"""
Login all accounts from Supabase — visible browser, saves cookies.
Run this on a new machine after git clone to establish sessions.

Usage:
    python tools/login_all.py              # login all accounts
    python tools/login_all.py --role follow # only follow accounts
    python tools/login_all.py --username tisiolik  # single account
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage import get_all_accounts, get_account_by_username
from core.session import open_session, close_session, needs_login, do_login


def login_account(account):
    """Login a single account with visible browser, save cookies."""
    username = account["username"]
    password = account.get("password", "")
    role = account.get("role", "follow")

    if not password:
        print(f"  SKIP @{username} — no password stored")
        return False

    print(f"\n{'='*50}")
    print(f"  Logging in @{username} (role={role})")
    print(f"{'='*50}")

    session = open_session(account, headless=False, no_proxy=True, block_images=False)
    page = session.page

    try:
        if needs_login(page):
            print(f"  Not logged in — entering credentials...")
            success = do_login(page, username, password)
            if success:
                print(f"  OK — @{username} logged in")
                # Wait a bit to let Instagram settle
                time.sleep(3)
            else:
                print(f"  FAILED — @{username} login failed")
                print(f"  Browser stays open 30s for manual intervention...")
                time.sleep(30)
        else:
            print(f"  Already logged in via cookies")
            success = True

        close_session(session, save_cookies=True)
        return success

    except Exception as e:
        print(f"  ERROR — @{username}: {e}")
        try:
            close_session(session, save_cookies=False)
        except:
            pass
        return False


def main():
    parser = argparse.ArgumentParser(description="Login all Instagram accounts")
    parser.add_argument("--role", help="Only login accounts with this role")
    parser.add_argument("--username", help="Login a single account by username")
    args = parser.parse_args()

    if args.username:
        account = get_account_by_username(args.username)
        if not account:
            print(f"Account @{args.username} not found in Supabase")
            return
        accounts = [account]
    else:
        accounts = get_all_accounts(role=args.role)

    print(f"\nAccounts to login: {len(accounts)}")
    for a in accounts:
        print(f"  @{a['username']} (role={a.get('role', 'follow')})")

    success = 0
    failed = 0

    for i, account in enumerate(accounts):
        print(f"\n--- Account {i+1}/{len(accounts)} ---")
        if login_account(account):
            success += 1
        else:
            failed += 1

        # Wait between accounts
        if i < len(accounts) - 1:
            wait = 5
            print(f"  Waiting {wait}s before next account...")
            time.sleep(wait)

    print(f"\n{'='*50}")
    print(f"  DONE: {success} logged in, {failed} failed")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
