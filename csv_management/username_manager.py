"""
Manage username tracking - mark as used, check status, get unused
"""

import csv
import os
from pathlib import Path


class UsernameTracker:
    """Manage username usage tracking from CSV file"""
    
    def __init__(self, tracker_file=None):
        if tracker_file is None:
            # Default: look for tracker file in same directory as this script
            tracker_file = os.path.join(os.path.dirname(__file__), "usernames_tracker.csv")
        
        self.tracker_file = tracker_file
        if not os.path.exists(tracker_file):
            print(f"⚠️ {tracker_file} not found! Run csv_merger.py first.")
        
    def load_usernames(self):
        """Load all usernames from tracker file"""
        usernames = {}
        try:
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    username = row.get('username', '').strip()
                    used = row.get('used', 'false').lower() == 'true'
                    if username:
                        usernames[username] = used
        except Exception as e:
            print(f"❌ Error reading tracker file: {e}")
        
        return usernames
    
    def save_usernames(self, usernames):
        """Save usernames to tracker file"""
        try:
            with open(self.tracker_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['username', 'used'])
                for username, used in sorted(usernames.items()):
                    writer.writerow([username, used])
            return True
        except Exception as e:
            print(f"❌ Error saving tracker file: {e}")
            return False
    
    def mark_as_used(self, username):
        """Mark a username as used"""
        usernames = self.load_usernames()
        
        if username not in usernames:
            print(f"⚠️ Username '{username}' not found in tracker!")
            return False
        
        usernames[username] = True
        if self.save_usernames(usernames):
            print(f"✓ Marked '{username}' as used")
            return True
        return False
    
    def mark_as_unused(self, username):
        """Mark a username as unused (reset)"""
        usernames = self.load_usernames()
        
        if username not in usernames:
            print(f"⚠️ Username '{username}' not found in tracker!")
            return False
        
        usernames[username] = False
        if self.save_usernames(usernames):
            print(f"✓ Marked '{username}' as unused")
            return True
        return False
    
    def get_unused_usernames(self, limit=None):
        """Get list of unused usernames"""
        usernames = self.load_usernames()
        unused = [u for u, used in usernames.items() if not used]
        
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
                status = "✓ USED" if usernames[username] else "⚟ UNUSED"
                print(f"Username: '{username}' -> {status}")
                return usernames[username]
            else:
                print(f"⚠️ Username '{username}' not found!")
                return None
        else:
            # Show stats
            total = len(usernames)
            used = sum(1 for u in usernames.values() if u)
            unused = total - used
            
            print(f"\n{'='*50}")
            print(f"Tracker Stats:")
            print(f"{'='*50}")
            print(f"Total usernames: {total}")
            print(f"Used: {used}")
            print(f"Unused: {unused}")
            print(f"{'='*50}\n")
            
            return {'total': total, 'used': used, 'unused': unused}
    
    def add_username(self, username):
        """Add a new username to tracker"""
        usernames = self.load_usernames()
        
        if username in usernames:
            print(f"⚠️ Username '{username}' already in tracker!")
            return False
        
        usernames[username] = False
        if self.save_usernames(usernames):
            print(f"✓ Added '{username}' to tracker")
            return True
        return False
    
    def remove_username(self, username):
        """Remove a username from tracker"""
        usernames = self.load_usernames()
        
        if username not in usernames:
            print(f"⚠️ Username '{username}' not found!")
            return False
        
        del usernames[username]
        if self.save_usernames(usernames):
            print(f"✓ Removed '{username}' from tracker")
            return True
        return False


if __name__ == "__main__":
    # Example usage
    tracker = UsernameTracker()
    
    # Get stats
    tracker.get_status()
    
    # Get next unused username
    next_username = tracker.get_next_unused()
    if next_username:
        print(f"Next unused username: {next_username}")
