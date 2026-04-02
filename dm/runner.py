"""
CLI entry point for the DM pipeline.
Usage: python -m dm.runner [options]
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dm.pipeline import run_dm_pipeline


def main():
    parser = argparse.ArgumentParser(description="Instagram DM Automation Pipeline (API)")
    parser.add_argument("--max-accounts", type=int, default=None,
                        help="Max accounts to process (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without sending DMs")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed (visible) mode")
    args = parser.parse_args()

    result = run_dm_pipeline(
        max_accounts=args.max_accounts,
        dry_run=args.dry_run,
        headless=not args.headed,
    )

    return result


if __name__ == "__main__":
    main()
