"""
Manage username tracking - mark as used, check status, get unused.
Tracks which of our accounts followed each target and when.

CSV columns: username;used;followed_by;followed_at
"""

import csv
import os
from datetime import datetime
from pathlib import Path


FIELDNAMES = ['username', 'used', 'followed_by', 'followed_at']


class UsernameTracker:
    """Manage username usage tracking from CSV file"""

    def __init__(self, tracker_file=None):
        if tracker_file is None:
            tracker_file = os.path.join(os.path.dirname(__file__),
                                        "csv_files", "usernames_tracker.csv")
        self.tracker_file = tracker_file
        if not os.path.exists(tracker_file):
            print(f"⚠️ {tracker_file} not found! Run the scraper first.")

    def load_usernames(self):
        """Load all usernames from tracker file

        Returns:
            dict: {username: {"used": bool, "followed_by": str, "followed_at": str}}
        """
        usernames = {}
        if not os.path.exists(self.tracker_file):
            return usernames
        try:
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    username = row.get('username', '').strip()
                    if username:
                        usernames[username] = {
                            "used": row.get('used', 'false').lower() == 'true',
                            "followed_by": row.get('followed_by', ''),
                            "followed_at": row.get('followed_at', ''),
                        }
        except Exception as e:
            print(f"❌ Error reading tracker file: {e}")
        return usernames

    def _save_all(self, usernames):
        """Write full tracker dict to CSV"""
        try:
            os.makedirs(os.path.dirname(self.tracker_file), exist_ok=True)
            with open(self.tracker_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=';')
                writer.writeheader()
                for uname in sorted(usernames):
                    info = usernames[uname]
                    writer.writerow({
                        'username': uname,
                        'used': info['used'],
                        'followed_by': info.get('followed_by', ''),
                        'followed_at': info.get('followed_at', ''),
                    })
            return True
        except Exception as e:
            print(f"❌ Error saving tracker file: {e}")
            return False

    # --- backward compat wrapper ---
    def save_usernames(self, usernames):
        """Save usernames (accepts old dict format too)"""
        # Convert old {username: bool} to new format
        converted = {}
        for k, v in usernames.items():
            if isinstance(v, dict):
                converted[k] = v
            else:
                converted[k] = {"used": v, "followed_by": "", "followed_at": ""}
        return self._save_all(converted)

    def exists(self, username):
        """Check if a username is already in the tracker"""
        return username in self.load_usernames()

    def mark_as_used(self, username, followed_by=""):
        """Mark a username as followed by a specific account"""
        usernames = self.load_usernames()

        if username not in usernames:
            # Auto-add if not present
            usernames[username] = {"used": False, "followed_by": "", "followed_at": ""}

        usernames[username]["used"] = True
        usernames[username]["followed_by"] = followed_by
        usernames[username]["followed_at"] = datetime.now().isoformat()

        if self._save_all(usernames):
            print(f"✓ Marked '{username}' as followed by @{followed_by}")
            return True
        return False

    def mark_as_unused(self, username):
        """Mark a username as unused (reset)"""
        usernames = self.load_usernames()

        if username not in usernames:
            print(f"⚠️ Username '{username}' not found in tracker!")
            return False

        usernames[username]["used"] = False
        usernames[username]["followed_by"] = ""
        usernames[username]["followed_at"] = ""

        if self._save_all(usernames):
            print(f"✓ Marked '{username}' as unused")
            return True
        return False

    def get_unused_usernames(self, limit=None):
        """Get list of unused usernames"""
        usernames = self.load_usernames()
        unused = [u for u, info in usernames.items() if not info['used']]

        if limit:
            return unused[:limit]
        return unused

    def get_next_unused(self):
        """Get the first unused username"""
        unused = self.get_unused_usernames(limit=1)
        return unused[0] if unused else None

    def get_status(self, username=None):
        """Get status of usernames"""
        usernames = self.load_usernames()

        if username:
            if username in usernames:
                info = usernames[username]
                if info['used']:
                    status = f"✓ FOLLOWED by @{info['followed_by']} at {info['followed_at']}"
                else:
                    status = "⚟ UNUSED"
                print(f"Username: '{username}' -> {status}")
                return info['used']
            else:
                print(f"⚠️ Username '{username}' not found!")
                return None
        else:
            total = len(usernames)
            used = sum(1 for info in usernames.values() if info['used'])
            unused = total - used

            print(f"\n{'='*50}")
            print(f"Tracker Stats:")
            print(f"{'='*50}")
            print(f"Total usernames: {total}")
            print(f"Followed: {used}")
            print(f"Unused: {unused}")
            print(f"{'='*50}\n")

            return {'total': total, 'used': used, 'unused': unused}

    def add_username(self, username):
        """Add a new username to tracker (skip if exists)"""
        usernames = self.load_usernames()

        if username in usernames:
            return False  # Already exists, skip silently

        usernames[username] = {"used": False, "followed_by": "", "followed_at": ""}
        return self._save_all(usernames)

    def add_usernames_bulk(self, username_list):
        """Add multiple usernames, skipping duplicates. Returns count of new adds."""
        usernames = self.load_usernames()
        new_count = 0
        for uname in username_list:
            if uname not in usernames:
                usernames[uname] = {"used": False, "followed_by": "", "followed_at": ""}
                new_count += 1
        if new_count > 0:
            self._save_all(usernames)
        return new_count

    def remove_username(self, username):
        """Remove a username from tracker"""
        usernames = self.load_usernames()

        if username not in usernames:
            print(f"⚠️ Username '{username}' not found!")
            return False

        del usernames[username]
        if self._save_all(usernames):
            print(f"✓ Removed '{username}' from tracker")
            return True
        return False


if __name__ == "__main__":
    tracker = UsernameTracker()
    tracker.get_status()
