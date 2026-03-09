#!/usr/bin/env python3
"""CLI shim — forwards to core.proxy CLI"""
import sys
from core.proxy import (
    get_fresh_proxy, force_rotate, test_proxy,
    get_all_active_sessions, test_current_proxies,
)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_current_proxies()
    elif len(sys.argv) > 1 and sys.argv[1] == "rotate":
        username = sys.argv[2] if len(sys.argv) > 2 else "_test"
        url = force_rotate(username)
        print(f"  New proxy: {url[:60]}...")
        test_proxy(url)
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        sessions = get_all_active_sessions()
        if not sessions:
            print("No active proxy sessions.")
        else:
            print(f"\n{'='*60}")
            for s in sessions:
                status = "EXPIRED" if s['expired'] else f"ACTIVE ({s['remaining']})"
                print(f"  @{s['username']:20s} session={s['session_id']:12s} {status}")
            print(f"{'='*60}")
    else:
        print("Usage:")
        print("  python proxy_manager.py test     -- test all active proxies")
        print("  python proxy_manager.py rotate   -- force-rotate to new IP")
        print("  python proxy_manager.py status   -- show active sessions")
