"""
Quick test: send a single DM via browser.

Usage:
    python test_dm.py <target_username> "your message here"
    python test_dm.py davematosyan "hey testing DMs!"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.browser_dm import send_dm


def main():
    if len(sys.argv) < 3:
        print("Usage: python test_dm.py <target_username> \"message text\"")
        sys.exit(1)

    target = sys.argv[1]
    message = sys.argv[2]

    # Get first non-scraper account
    accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]
    if not accounts:
        print("No accounts found!")
        sys.exit(1)

    account = accounts[0]
    print(f"Using account: @{account['username']}")
    print(f"Target: @{target}")
    print(f"Message: {message}")
    print()

    session = open_session(account, headless=False)

    try:
        if not ensure_logged_in(session):
            print("Login failed!")
            return

        print("\nSending DM...")
        ok = send_dm(session.page, target, message)
        print(f"\nResult: {'SUCCESS' if ok else 'FAILED'}")

        input("\nPress Enter to close browser...")

    finally:
        close_session(session)


if __name__ == "__main__":
    main()
