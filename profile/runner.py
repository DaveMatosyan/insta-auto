"""
CLI entry point for profile setup.
Usage: python -m profile.runner [options]
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FANVUE_LINK


def main():
    parser = argparse.ArgumentParser(description="Instagram Profile Setup (API)")
    parser.add_argument("--linktree", type=str, default=FANVUE_LINK,
                        help=f"Linktree URL for bio (default: {FANVUE_LINK})")
    parser.add_argument("--posts", type=int, default=6,
                        help="Posts per account (default: 6)")
    parser.add_argument("--max-accounts", type=int, default=None,
                        help="Max accounts to process")
    args = parser.parse_args()

    from core.storage import get_all_accounts
    from profile.setup import setup_account_profile

    accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]
    if args.max_accounts:
        accounts = accounts[:args.max_accounts]

    print(f"\nProfile Setup: {len(accounts)} accounts, {args.posts} posts each")
    print(f"Linktree: {args.linktree}\n")

    import random, time
    for i, account in enumerate(accounts):
        setup_account_profile(account, args.linktree, args.posts)
        if i < len(accounts) - 1:
            wait = random.uniform(30, 60)
            print(f"\nWaiting {wait:.0f}s before next account...")
            time.sleep(wait)


if __name__ == "__main__":
    main()
