"""
Daily follow system — login via cookies, follow targets, track usage.
Uses ramp-based daily limits instead of a flat number.
"""

import random
import time
import os

from config import PROJECT_ROOT
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


def follow_targets(session, targets, account_username, count=None):
    """
    Follow up to `count` target usernames.

    Args:
        session: Session object from core.session
        targets: list of usernames to follow
        account_username: the account doing the following (for recording)
        count: max follows (if None, follow all targets given)

    Returns:
        list of successfully followed usernames
    """
    page = session.page
    followed = []
    to_follow = targets[:count] if count else targets

    for target in to_follow:
        try:
            print(f"  -> Following @{target}...")
            page.goto(f"https://www.instagram.com/{target}/", wait_until="domcontentloaded", timeout=15000)
            human_delay(3, 5)

            follow_btn = page.locator('button:has-text("Follow")').first
            if follow_btn.is_visible(timeout=3000):
                btn_text = follow_btn.inner_text()
                if btn_text.strip() in ("Following", "Requested"):
                    print(f"     Already following/requested @{target}, skipping")
                    continue
                follow_btn.click()
                human_delay(2, 4)
                print(f"     Followed @{target}")
                followed.append(target)

                # Record in Supabase
                try:
                    record_follow(account_username, target)
                except Exception as e:
                    print(f"     Warning: failed to record follow in Supabase: {e}")
            else:
                print(f"     No Follow button for @{target} (private/nonexistent?)")

        except Exception as e:
            print(f"     Error following @{target}: {e}")

        if target != to_follow[-1]:
            wait = random.uniform(30, 90)
            print(f"     Waiting {wait:.0f}s before next follow...")
            time.sleep(wait)

    return followed


def run_daily_follows(max_accounts=None, dry_run=False, headless=True):
    """
    Main entry point — run follows for all (or some) accounts.
    Uses ramp-based daily limits.

    Returns:
        dict with summary stats
    """
    # Reset daily counts at the start of each run
    reset_daily_counts()

    # Get account credentials from JSON
    accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]
    if max_accounts:
        accounts = accounts[:max_accounts]

    # Get ramp info from Supabase
    active_ramp = get_all_active_accounts()
    ramp_by_username = {a["username"]: a for a in active_ramp}

    tracker = UsernameTracker()
    unused = tracker.get_unused_usernames()

    if not unused:
        print("No unused target usernames left!")
        return {"accounts": 0, "follows": 0, "errors": 0}

    print(f"\n{'='*60}")
    print(f"DAILY FOLLOW RUN (RAMP-BASED)")
    print(f"Accounts: {len(accounts)}")
    print(f"Targets available: {len(unused)}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*60}")
    for account in accounts:
        ramp = ramp_by_username.get(account.get("username", ""))
        if ramp:
            print(f"  @{ramp['username']}: Phase {ramp['phase']} | "
                  f"Limit {ramp['daily_limit']}/day | "
                  f"Done today: {ramp['daily_follows_today']} | "
                  f"Remaining: {ramp['remaining']} | "
                  f"Total: {ramp['total_follows']}")
        else:
            print(f"  @{account.get('username', '???')}: NOT IN SUPABASE")
    print(f"{'='*60}\n")

    total_follows = 0
    total_errors = 0
    offset = 0

    for i, account in enumerate(accounts):
        username = account.get("username", "???")
        ramp = ramp_by_username.get(username)

        if not ramp:
            print(f"\n--- Account {i+1}/{len(accounts)}: @{username} ---")
            print(f"    Not found in Supabase accounts table, skipping")
            continue

        allowance = ramp["remaining"]
        if allowance <= 0:
            print(f"\n--- Account {i+1}/{len(accounts)}: @{username} ---")
            print(f"    Already at daily limit ({ramp['daily_limit']}), skipping")
            continue

        targets_slice = unused[offset:offset + allowance]
        offset += allowance

        if not targets_slice:
            print(f"Ran out of target usernames at account {i+1}")
            break

        print(f"\n--- Account {i+1}/{len(accounts)}: @{username} ---")
        print(f"    Phase {ramp['phase']} | Allowance: {allowance} | Targets: {len(targets_slice)}")

        if dry_run:
            print(f"    [DRY RUN] Would follow {len(targets_slice)} targets")
            total_follows += len(targets_slice)
            continue

        try:
            session = open_session(account, headless=headless, block_images=True)

            if not ensure_logged_in(session):
                print(f"    Could not log in as @{username}, skipping")
                close_session(session, save_cookies=False)
                total_errors += 1
                continue

            followed = follow_targets(session, targets_slice, username)
            total_follows += len(followed)

            for t in followed:
                tracker.mark_as_used(t, followed_by=username)

            close_session(session, save_cookies=True)

        except Exception as e:
            print(f"    Session error for @{username}: {e}")
            total_errors += 1

        if i < len(accounts) - 1:
            wait = random.uniform(60, 120)
            print(f"\nWaiting {wait:.0f}s before next account...")
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
