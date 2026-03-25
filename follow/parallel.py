"""
Parallel follow — open N accounts simultaneously, each follows its ramp allowance.
Each account gets its own visible browser window.

Usage:
    python parallel_follow.py --accounts 2
    python parallel_follow.py --accounts 4 --dry-run
"""

import argparse
import random
import time
import os
import threading
from datetime import datetime

from config import PROJECT_ROOT, SESSIONS_DIR
from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.utils import human_delay
from csv_management.username_manager import UsernameTracker
from follow.ramp import (
    get_account_allowance,
    get_all_active_accounts,
    record_follow,
    reset_daily_counts,
    get_phase_info,
)


def follow_targets_for_account(account, targets, result_store, lock):
    """
    Open a visible browser for one account and follow its targets.
    Runs in its own thread.
    """
    username = account.get("username", "???")
    followed = []
    errors = 0

    print(f"\n[{username}] Starting -- {len(targets)} targets to follow")

    try:
        session = open_session(account, headless=False, block_images=True)

        if not ensure_logged_in(session):
            print(f"[{username}] Could not log in, skipping")
            close_session(session, save_cookies=False)
            with lock:
                result_store[username] = {"followed": [], "errors": 1}
            return

        page = session.page

        for i, target in enumerate(targets):
            try:
                print(f"[{username}] [{i+1}/{len(targets)}] -> @{target}")
                page.goto(f"https://www.instagram.com/{target}/",
                          wait_until="domcontentloaded", timeout=20000)
                human_delay(3, 5)

                follow_btn = page.locator('button:has-text("Follow")').first
                if follow_btn.is_visible(timeout=4000):
                    btn_text = follow_btn.inner_text().strip()
                    if btn_text in ("Following", "Requested"):
                        print(f"[{username}]    Already following @{target}")
                        continue
                    follow_btn.click()
                    human_delay(2, 4)
                    print(f"[{username}]    Followed @{target}")
                    followed.append(target)

                    # Record in Supabase
                    try:
                        record_follow(username, target)
                    except Exception as e:
                        print(f"[{username}]    Warning: failed to record follow in Supabase: {e}")
                else:
                    print(f"[{username}]    No Follow button for @{target}")

            except Exception as e:
                print(f"[{username}]    Error on @{target}: {e}")
                errors += 1

            if i < len(targets) - 1:
                wait = random.uniform(25, 55)
                print(f"[{username}]    {wait:.0f}s before next...")
                time.sleep(wait)

        close_session(session, save_cookies=True)
        print(f"\n[{username}] Done -- followed {len(followed)}/{len(targets)}")

    except Exception as e:
        print(f"[{username}] Session failed: {e}")
        errors += 1

    with lock:
        result_store[username] = {"followed": followed, "errors": errors}


def run_parallel_follows(num_accounts=2, dry_run=False):
    """
    Run parallel follows for N accounts using ramp-based allowances.
    Each account's follow count is determined by its ramp phase.
    """
    # Reset daily counts at the start of each run
    reset_daily_counts()

    # Get account credentials from JSON
    all_accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]

    # Get ramp info from Supabase
    active_ramp = get_all_active_accounts()
    ramp_by_username = {a["username"]: a for a in active_ramp}

    # Sort by session file size (most established sessions first)
    accounts_sorted = sorted(
        all_accounts,
        key=lambda a: os.path.getsize(os.path.join(SESSIONS_DIR, f"{a['username']}_state.json"))
                      if os.path.exists(os.path.join(SESSIONS_DIR, f"{a['username']}_state.json")) else 0,
        reverse=True
    )

    # Filter to only active accounts that have remaining allowance
    selected = []
    for a in accounts_sorted:
        username = a["username"]
        ramp = ramp_by_username.get(username)
        if ramp and ramp["remaining"] > 0:
            selected.append(a)
        if len(selected) >= num_accounts:
            break

    if not selected:
        print("No accounts with remaining allowance today!")
        return

    tracker = UsernameTracker()
    unused = tracker.get_unused_usernames()

    # Show ramp status
    print(f"\n{'='*60}")
    print(f"PARALLEL FOLLOW (RAMP-BASED)")
    print(f"Accounts: {len(selected)}")
    print(f"Targets available: {len(unused)}")
    print(f"Mode: VISIBLE browsers")
    print(f"{'='*60}")
    for a in selected:
        ramp = ramp_by_username[a["username"]]
        info = ramp["phase_info"]
        print(f"  @{a['username']}: Phase {ramp['phase']} | "
              f"Limit {ramp['daily_limit']}/day | "
              f"Done today: {ramp['daily_follows_today']} | "
              f"Remaining: {ramp['remaining']} | "
              f"Total: {ramp['total_follows']}")
    print(f"{'='*60}\n")

    # Assign targets to each account based on their remaining allowance
    account_targets = {}
    offset = 0
    for account in selected:
        ramp = ramp_by_username[account["username"]]
        count = ramp["remaining"]
        account_targets[account["username"]] = unused[offset:offset + count]
        offset += count
        print(f"@{account['username']} -> {len(account_targets[account['username']])} targets")

    if dry_run:
        print("\n[DRY RUN] No follows will be executed.")
        for username, targets in account_targets.items():
            print(f"  @{username}: would follow {len(targets)} targets")
        return

    print()

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
            daemon=True
        )
        threads.append(t)

    print("Launching all browsers simultaneously...\n")
    for t in threads:
        t.start()
        time.sleep(2)

    for t in threads:
        t.join()

    # Mark follows in the username tracker
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
    parser.add_argument("--accounts", type=int, default=2, help="Number of accounts to run in parallel")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would happen without acting")
    args = parser.parse_args()

    run_parallel_follows(num_accounts=args.accounts, dry_run=args.dry_run)
