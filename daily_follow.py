#!/usr/bin/env python3
"""CLI shim — forwards to follow.daily"""
from follow.daily import run_daily_follows

if __name__ == "__main__":
    run_daily_follows()
