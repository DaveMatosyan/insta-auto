#!/usr/bin/env python3
"""CLI shim — forwards to follow.parallel"""
import argparse
from follow.parallel import run_parallel_follows

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", type=int, default=2, help="Number of accounts to run in parallel")
    parser.add_argument("--follows", type=int, default=10, help="Follows per account")
    args = parser.parse_args()
    run_parallel_follows(num_accounts=args.accounts, follows_per_account=args.follows)
