#!/usr/bin/env python
"""
Command-line utility for managing usernames quickly
Run: python username_cli.py <command> [args]
"""

import sys
from username_manager import UsernameTracker


def show_help():
    """Show help message"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║          USERNAME TRACKER - COMMAND LINE UTILITY              ║
╚════════════════════════════════════════════════════════════════╝

USAGE:
  python username_cli.py <command> [arguments]

COMMANDS:

  status                  - Show tracker stats (total, used, unused)
  next                    - Get next unused username
  list [limit]            - List unused usernames (default: 20)
  mark-used <username>    - Mark username as used (true)
  mark-unused <username>  - Mark username as unused (false)
  check <username>        - Check status of a specific username
  add <username>          - Add new username to tracker
  remove <username>       - Remove username from tracker
  help                    - Show this help message

EXAMPLES:

  python username_cli.py status
    → Shows: Total: 2450, Used: 150, Unused: 2300

  python username_cli.py next
    → Shows: zalalagram

  python username_cli.py list 10
    → Shows next 10 unused usernames

  python username_cli.py mark-used gary_b_runs
    → Marks gary_b_runs as used

  python username_cli.py check fordesgolf
    → Shows: Username: 'fordesgolf' -> ⚟ UNUSED

  python username_cli.py add john_doe
    → Adds john_doe to tracker

═════════════════════════════════════════════════════════════════
""")


def main():
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    tracker = UsernameTracker()
    
    # ==================== STATUS ====================
    if command == "status":
        tracker.get_status()
    
    # ==================== NEXT ====================
    elif command == "next":
        username = tracker.get_next_unused()
        if username:
            print(f"Next unused: {username}")
        else:
            print("❌ No unused usernames available!")
    
    # ==================== LIST ====================
    elif command == "list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        unused = tracker.get_unused_usernames(limit=limit)
        
        if not unused:
            print("❌ No unused usernames available!")
            return
        
        print(f"\nUnused usernames (first {len(unused)}):")
        print("─" * 50)
        for i, username in enumerate(unused, 1):
            print(f"{i:3d}. {username}")
        print(f"\nTotal shown: {len(unused)}\n")
    
    # ==================== MARK-USED ====================
    elif command == "mark-used":
        if len(sys.argv) < 3:
            print("❌ Usage: python username_cli.py mark-used <username>")
            return
        username = sys.argv[2]
        tracker.mark_as_used(username)
    
    # ==================== MARK-UNUSED ====================
    elif command == "mark-unused":
        if len(sys.argv) < 3:
            print("❌ Usage: python username_cli.py mark-unused <username>")
            return
        username = sys.argv[2]
        tracker.mark_as_unused(username)
    
    # ==================== CHECK ====================
    elif command == "check":
        if len(sys.argv) < 3:
            print("❌ Usage: python username_cli.py check <username>")
            return
        username = sys.argv[2]
        tracker.get_status(username)
    
    # ==================== ADD ====================
    elif command == "add":
        if len(sys.argv) < 3:
            print("❌ Usage: python username_cli.py add <username>")
            return
        username = sys.argv[2]
        tracker.add_username(username)
    
    # ==================== REMOVE ====================
    elif command == "remove":
        if len(sys.argv) < 3:
            print("❌ Usage: python username_cli.py remove <username>")
            return
        username = sys.argv[2]
        tracker.remove_username(username)
    
    # ==================== HELP ====================
    elif command == "help":
        show_help()
    
    else:
        print(f"❌ Unknown command: {command}")
        print("Use 'python username_cli.py help' for available commands")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
