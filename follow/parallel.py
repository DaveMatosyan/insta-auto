"""
Parallel follow — open N accounts simultaneously, each follows X targets.
Each account gets its own visible browser window.

Usage:
    python parallel_follow.py --accounts 2 --follows 10
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


def run_parallel_follows(num_accounts=2, follows_per_account=10):
    accounts = get_all_accounts()

    accounts_sorted = sorted(
        accounts,
        key=lambda a: os.path.getsize(os.path.join(SESSIONS_DIR, f"{a['username']}_state.json"))
                      if os.path.exists(os.path.join(SESSIONS_DIR, f"{a['username']}_state.json")) else 0,
        reverse=True
    )
    selected = accounts_sorted[:num_accounts]

    if not selected:
        print("No accounts available!")
        return

    tracker = UsernameTracker()
    unused = tracker.get_unused_usernames()

    if len(unused) < num_accounts * follows_per_account:
        print(f"Only {len(unused)} targets available, need {num_accounts * follows_per_account}")

    print(f"\n{'='*60}")
    print(f"PARALLEL FOLLOW")
    print(f"Accounts: {num_accounts} -- {[a['username'] for a in selected]}")
    print(f"Follows per account: {follows_per_account}")
    print(f"Targets available: {len(unused)}")
    print(f"Mode: VISIBLE browsers")
    print(f"{'='*60}\n")

    account_targets = {}
    for i, account in enumerate(selected):
        start = i * follows_per_account
        end = start + follows_per_account
        account_targets[account['username']] = unused[start:end]
        print(f"@{account['username']} -> {account_targets[account['username']]}")

    print()

    threads = []
    results = {}
    lock = threading.Lock()

    for account in selected:
        targets = account_targets[account['username']]
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

    for account in selected:
        username = account['username']
        result = results.get(username, {})
        for target in result.get('followed', []):
            tracker.mark_as_used(target, followed_by=username)

    total_followed = sum(len(r.get('followed', [])) for r in results.values())
    total_errors = sum(r.get('errors', 0) for r in results.values())

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
    parser.add_argument("--follows", type=int, default=10, help="Follows per account")
    args = parser.parse_args()

    run_parallel_follows(num_accounts=args.accounts, follows_per_account=args.follows)
