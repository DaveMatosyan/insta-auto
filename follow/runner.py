"""
Daily orchestrator — run follows for all accounts, log results.

Usage:
    python run_daily.py              # run follows for all accounts
    python run_daily.py --accounts 3 # run for first 3 accounts only
    python run_daily.py --dry-run    # preview what would happen
"""

import argparse
import os
import logging
from datetime import datetime

from config import LOGS_DIR
from follow.daily import run_daily_follows


def setup_logging():
    """Set up file + console logging."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"daily_{datetime.now().strftime('%Y-%m-%d')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )
    return log_file


def main():
    parser = argparse.ArgumentParser(description="Run daily Instagram follow automation")
    parser.add_argument("--accounts", type=int, default=None, help="Limit to first N accounts")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would happen without acting")
    args = parser.parse_args()

    log_file = setup_logging()
    logging.info(f"Log file: {log_file}")
    logging.info(f"Accounts: {'all' if args.accounts is None else args.accounts}")
    logging.info(f"Dry run: {args.dry_run}")

    summary = run_daily_follows(max_accounts=args.accounts, dry_run=args.dry_run)

    logging.info(f"Done -- {summary['follows']} follows, {summary['errors']} errors")


if __name__ == "__main__":
    main()
