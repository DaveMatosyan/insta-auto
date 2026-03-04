"""
Daily follow system — login via cookies, follow targets, track usage.
"""

import random
import time
from config import DAILY_FOLLOWS_PER_ACCOUNT
from account_storage import get_all_accounts
from session_manager import open_session, close_session, ensure_logged_in
import os
from csv_management.username_manager import UsernameTracker

TRACKER_CSV = os.path.join(os.path.dirname(__file__), "csv_management", "csv_files", "usernames_tracker.csv")


def human_delay(min_sec=1, max_sec=3):
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def follow_targets(session, targets, count=None):
    """
    Follow up to `count` target usernames.

    Args:
        session: Session object from session_manager
        targets: list of usernames to follow
        count: max follows (default: DAILY_FOLLOWS_PER_ACCOUNT)

    Returns:
        list of successfully followed usernames
    """
    if count is None:
        count = DAILY_FOLLOWS_PER_ACCOUNT

    page = session.page
    followed = []

    for target in targets[:count]:
        try:
            print(f"  -> Following @{target}...")
            page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=15000)
            human_delay(3, 5)

            # Find Follow button (skip if already following)
            follow_btn = page.locator('button:has-text("Follow")').first
            if follow_btn.is_visible(timeout=3000):
                btn_text = follow_btn.inner_text()
                if btn_text.strip() in ("Following", "Requested"):
                    print(f"     Already following/requested @{target}, skipping")
                    continue
                follow_btn.click()
                human_delay(2, 4)
                print(f"     ✅ Followed @{target}")
                followed.append(target)
            else:
                print(f"     ⚠️ No Follow button for @{target} (private/nonexistent?)")

        except Exception as e:
            print(f"     ❌ Error following @{target}: {e}")

        # Wait between follows (30-90s for safety)
        if target != targets[min(count, len(targets)) - 1]:
            wait = random.uniform(30, 90)
            print(f"     ⏳ Waiting {wait:.0f}s before next follow...")
            time.sleep(wait)

    return followed


def run_daily_follows(max_accounts=None, dry_run=False, headless=True):
    """
    Main entry point — run follows for all (or some) accounts.

    Args:
        max_accounts: Limit to first N accounts (None = all)
        dry_run: If True, just preview what would happen
        headless: If False, show browser window (default True)

    Returns:
        dict with summary stats
    """
    accounts = get_all_accounts()
    if max_accounts:
        accounts = accounts[:max_accounts]

    tracker = UsernameTracker(TRACKER_CSV)
    unused = tracker.get_unused_usernames()

    if not unused:
        print("❌ No unused target usernames left!")
        return {"accounts": 0, "follows": 0, "errors": 0}

    print(f"\n{'='*60}")
    print(f"DAILY FOLLOW RUN")
    print(f"Accounts: {len(accounts)}")
    print(f"Targets available: {len(unused)}")
    print(f"Follows per account: {DAILY_FOLLOWS_PER_ACCOUNT}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*60}\n")

    total_follows = 0
    total_errors = 0
    offset = 0

    for i, account in enumerate(accounts):
        username = account.get("username", "???")
        targets_slice = unused[offset:offset + DAILY_FOLLOWS_PER_ACCOUNT]
        offset += DAILY_FOLLOWS_PER_ACCOUNT

        if not targets_slice:
            print(f"⚠️ Ran out of target usernames at account {i+1}")
            break

        print(f"\n--- Account {i+1}/{len(accounts)}: @{username} ---")
        print(f"    Targets: {targets_slice}")

        if dry_run:
            print(f"    [DRY RUN] Would follow {len(targets_slice)} targets")
            total_follows += len(targets_slice)
            continue

        # Open session with proxy + cookies
        try:
            session = open_session(account, headless=headless, block_images=True)

            if not ensure_logged_in(session):
                print(f"    ❌ Could not log in as @{username}, skipping")
                close_session(session, save_cookies=False)
                total_errors += 1
                continue

            followed = follow_targets(session, targets_slice)
            total_follows += len(followed)

            # Mark followed targets as used — record which account did it
            for t in followed:
                tracker.mark_as_used(t, followed_by=username)

            close_session(session, save_cookies=True)

        except Exception as e:
            print(f"    ❌ Session error for @{username}: {e}")
            total_errors += 1

        # Wait between accounts (60-120s)
        if i < len(accounts) - 1:
            wait = random.uniform(60, 120)
            print(f"\n⏳ Waiting {wait:.0f}s before next account...")
            time.sleep(wait)

    summary = {
        "accounts": len(accounts),
        "follows": total_follows,
        "errors": total_errors,
    }

    print(f"\n{'='*60}")
    print(f"DAILY FOLLOW SUMMARY")
    print(f"Accounts processed: {summary['accounts']}")
    print(f"Total follows: {summary['follows']}")
    print(f"Errors: {summary['errors']}")
    print(f"{'='*60}\n")

    return summary


if __name__ == "__main__":
    run_daily_follows()
