"""
Always-on follow scheduler — the PC 2 daemon.

Runs forever in a loop:
1. Every morning at a configured time, resets daily counts
2. For each active account, checks remaining allowance
3. Launches parallel browsers for all accounts with remaining allowance
4. After follows complete, sleeps until the next day
5. Logs to data/logs/scheduler_YYYY-MM-DD.log

Usage:
    python run_scheduler.py            # start the always-on daemon
    python run_scheduler.py --dry-run  # preview today's plan without following
    python run_scheduler.py --now      # run immediately (skip wait until scheduled time)
    python run_scheduler.py --status   # show ramp status for all accounts and exit
    python run_scheduler.py --time 10:30  # set daily run time (default: 09:00)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from config import PROJECT_ROOT, LOGS_DIR
from follow.ramp import (
    reset_daily_counts,
    get_all_active_accounts,
    get_phase_info,
)
from follow.parallel import run_parallel_follows


def setup_logging():
    """Set up file + console logging for the scheduler."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, f"scheduler_{datetime.now().strftime('%Y-%m-%d')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )
    return log_file


def print_status():
    """Print ramp status for all active accounts."""
    accounts = get_all_active_accounts()

    if not accounts:
        print("No active accounts found in Supabase.")
        return

    print(f"\n{'='*75}")
    print(f"  RAMP STATUS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*75}")
    print(f"  {'Username':<20} {'Phase':>5} {'Limit':>6} {'Today':>6} {'Left':>5} {'Total':>7} {'Last Run':<12}")
    print(f"  {'-'*20} {'-'*5} {'-'*6} {'-'*6} {'-'*5} {'-'*7} {'-'*12}")

    for a in accounts:
        last = a["last_follow_date"] or "never"
        print(f"  {a['username']:<20} {a['phase']:>5} {a['daily_limit']:>6} "
              f"{a['daily_follows_today']:>6} {a['remaining']:>5} {a['total_follows']:>7} {str(last):<12}")

    total = sum(a["total_follows"] for a in accounts)
    remaining = sum(a["remaining"] for a in accounts)
    print(f"  {'-'*20} {'-'*5} {'-'*6} {'-'*6} {'-'*5} {'-'*7} {'-'*12}")
    print(f"  {'TOTALS':<20} {'':>5} {'':>6} {'':>6} {remaining:>5} {total:>7}")
    print(f"{'='*75}\n")


def seconds_until(target_hour, target_minute):
    """Calculate seconds until the next occurrence of target_hour:target_minute."""
    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_scheduler(run_time="09:00", dry_run=False, run_now=False):
    """
    Main scheduler loop. Runs daily at the specified time.
    """
    hour, minute = map(int, run_time.split(":"))

    log_file = setup_logging()
    logging.info(f"Scheduler started — daily run at {run_time}")
    logging.info(f"Log file: {log_file}")
    logging.info(f"Dry run: {dry_run}")

    # Accounts are now stored directly in Supabase
    logging.info("Accounts loaded from Supabase")

    while True:
        if run_now:
            logging.info("--now flag set, running immediately")
            run_now = False  # only skip wait on first iteration
        else:
            wait = seconds_until(hour, minute)
            wake_time = datetime.now() + timedelta(seconds=wait)
            logging.info(f"Sleeping until {wake_time.strftime('%Y-%m-%d %H:%M')} ({wait / 3600:.1f} hours)")
            time.sleep(wait)

        # Rotate log file for new day
        log_file = os.path.join(LOGS_DIR, f"scheduler_{datetime.now().strftime('%Y-%m-%d')}.log")

        logging.info(f"\n{'='*60}")
        logging.info(f"DAILY RUN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logging.info(f"{'='*60}")

        # Show current status
        print_status()

        # Check how many accounts have remaining allowance
        accounts = get_all_active_accounts()
        accounts_with_allowance = [a for a in accounts if a["remaining"] > 0]

        if not accounts_with_allowance:
            logging.info("All accounts have hit their daily limits. Nothing to do.")
        else:
            total_remaining = sum(a["remaining"] for a in accounts_with_allowance)
            logging.info(f"{len(accounts_with_allowance)} accounts with remaining allowance "
                         f"({total_remaining} total follows to do)")

            # Run parallel follows for all accounts with remaining allowance
            run_parallel_follows(
                num_accounts=len(accounts_with_allowance),
                dry_run=dry_run,
            )

        logging.info("Daily run complete. Sleeping until tomorrow.\n")


def main():
    parser = argparse.ArgumentParser(description="Always-on follow scheduler daemon")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would happen without acting")
    parser.add_argument("--now", action="store_true", help="Run immediately instead of waiting for scheduled time")
    parser.add_argument("--status", action="store_true", help="Show ramp status and exit")
    parser.add_argument("--time", type=str, default="09:00", help="Daily run time in HH:MM format (default: 09:00)")
    args = parser.parse_args()

    if args.status:
        # Just show status and exit
        reset_daily_counts()
        print_status()
        return

    run_scheduler(run_time=args.time, dry_run=args.dry_run, run_now=args.now)


if __name__ == "__main__":
    main()
