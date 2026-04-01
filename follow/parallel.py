"""
Parallel follow — run N accounts simultaneously via browser, each follows its ramp allowance.

Usage:
    python parallel_follow.py --accounts 2
    python parallel_follow.py --accounts 4 --dry-run
"""

import argparse
import random
import time
import os
import threading

from config import PROJECT_ROOT, SESSIONS_DIR
from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.browser_follow import follow_user
from csv_management.username_manager import UsernameTracker
from follow.ramp import (
    get_all_active_accounts,
    record_follow,
    reset_daily_counts,
)


def follow_targets_for_account(account, targets, result_store, lock):
    """
    Follow targets for one account via browser. Runs in its own thread.
    """
    username = account.get("username", "???")
    followed = []
    errors = 0

    print(f"\n[{username}] Starting -- {len(targets)} targets to follow")

    session = None
    try:
        session = open_session(account, headless=True)

        if not ensure_logged_in(session):
            print(f"[{username}] Could not log in, skipping")
            with lock:
                result_store[username] = {"followed": [], "errors": 1}
            return

        page = session.page

        for i, target in enumerate(targets):
            try:
                print(f"[{username}] [{i+1}/{len(targets)}] -> @{target}")
                if follow_user(page, target):
                    print(f"[{username}]    Followed @{target}")
                    followed.append(target)

                    try:
                        record_follow(username, target)
                    except Exception as e:
                        print(f"[{username}]    Warning: failed to record: {e}")
                else:
                    print(f"[{username}]    Could not follow @{target}")

            except Exception as e:
                err = str(e).lower()
                if "challenge" in err:
                    print(f"[{username}]    Challenge! Stopping.")
                    errors += 1
                    break
                elif "rate" in err or "limit" in err:
                    print(f"[{username}]    Rate limited! Stopping.")
                    errors += 1
                    break
                else:
                    print(f"[{username}]    Error: {e}")
                    errors += 1

            if i < len(targets) - 1:
                wait = random.uniform(25, 55)
                print(f"[{username}]    {wait:.0f}s before next...")
                time.sleep(wait)

        print(f"\n[{username}] Done -- followed {len(followed)}/{len(targets)}")

    except Exception as e:
        print(f"[{username}] Failed: {e}")
        errors += 1

    finally:
        if session:
            close_session(session)

    with lock:
        result_store[username] = {"followed": followed, "errors": errors}


def run_parallel_follows(num_accounts=2, dry_run=False):
    """Run parallel follows for N accounts using ramp-based allowances."""
    reset_daily_counts()

    all_accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]
    active_ramp = get_all_active_accounts()
    ramp_by_username = {a["username"]: a for a in active_ramp}

    # Select accounts with remaining allowance
    selected = []
    for a in all_accounts:
        ramp = ramp_by_username.get(a["username"])
        if ramp and ramp["remaining"] > 0:
            selected.append(a)
        if len(selected) >= num_accounts:
            break

    if not selected:
        print("No accounts with remaining allowance today!")
        return

    tracker = UsernameTracker()
    unused = tracker.get_unused_usernames()

    print(f"\n{'='*60}")
    print(f"PARALLEL FOLLOW (BROWSER-BASED, RAMP)")
    print(f"Accounts: {len(selected)}")
    print(f"Targets available: {len(unused)}")
    print(f"{'='*60}")
    for a in selected:
        ramp = ramp_by_username[a["username"]]
        print(f"  @{a['username']}: Phase {ramp['phase']} | "
              f"Limit {ramp['daily_limit']}/day | "
              f"Remaining: {ramp['remaining']} | "
              f"Total: {ramp['total_follows']}")
    print(f"{'='*60}\n")

    # Assign targets
    account_targets = {}
    offset = 0
    for account in selected:
        ramp = ramp_by_username[account["username"]]
        count = ramp["remaining"]
        account_targets[account["username"]] = unused[offset:offset + count]
        offset += count

    if dry_run:
        print("[DRY RUN] No follows will be executed.")
        for username, targets in account_targets.items():
            print(f"  @{username}: would follow {len(targets)} targets")
        return

    threads = []
    results = {}
    lock = threading.Lock()

    for account in selected:
        targets = account_targets[account["username"]]
        if not targets:
            continue
        t = threading.Thread(
            target=follow_targets_for_account,
            args=(account, targets, results, lock),
            daemon=True,
        )
        threads.append(t)

    print("Launching all browser sessions simultaneously...\n")
    for t in threads:
        t.start()
        time.sleep(2)

    for t in threads:
        t.join()

    # Mark in tracker
    for account in selected:
        username = account["username"]
        result = results.get(username, {})
        for target in result.get("followed", []):
            tracker.mark_as_used(target, followed_by=username)

    total_followed = sum(len(r.get("followed", [])) for r in results.values())
    total_errors = sum(r.get("errors", 0) for r in results.values())

    print(f"\n{'='*60}")
    print(f"PARALLEL FOLLOW COMPLETE")
    for username, result in results.items():
        print(f"  @{username}: {len(result.get('followed', []))} followed, {result.get('errors', 0)} errors")
    print(f"Total followed: {total_followed}")
    print(f"Total errors: {total_errors}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_parallel_follows(num_accounts=args.accounts, dry_run=args.dry_run)
