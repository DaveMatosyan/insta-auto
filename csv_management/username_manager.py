"""
Manage username tracking — mark as used, check status, get unused.
Tracks which of our accounts followed each target and when.

Backend: Supabase `usernames_tracker` table
Columns: username (PK), used (bool), followed_by (text), followed_at (timestamptz)
"""

from datetime import datetime

from db.supabase_client import supabase

TABLE = "usernames_tracker"


class UsernameTracker:
    """Manage username usage tracking via Supabase"""

    def __init__(self, tracker_file=None):
        # tracker_file is accepted for backward compatibility but ignored
        pass

    def load_usernames(self):
        """Load all usernames from Supabase.

        Returns:
            dict: {username: {"used": bool, "followed_by": str, "followed_at": str}}
        """
        usernames = {}
        try:
            resp = supabase.table(TABLE).select("*").execute()
            for row in resp.data:
                usernames[row["username"]] = {
                    "used": row.get("used", False),
                    "followed_by": row.get("followed_by", ""),
                    "followed_at": row.get("followed_at", "") or "",
                }
        except Exception as e:
            print(f"❌ Error reading tracker from Supabase: {e}")
        return usernames

    def _save_all(self, usernames):
        """Write full tracker dict to Supabase (upsert all rows)"""
        try:
            rows = []
            for uname in sorted(usernames):
                info = usernames[uname]
                rows.append({
                    "username": uname,
                    "used": info["used"],
                    "followed_by": info.get("followed_by", ""),
                    "followed_at": info.get("followed_at") or None,
                })
            if rows:
                supabase.table(TABLE).upsert(rows).execute()
            return True
        except Exception as e:
            print(f"❌ Error saving tracker to Supabase: {e}")
            return False

    # --- backward compat wrapper ---
    def save_usernames(self, usernames):
        """Save usernames (accepts old dict format too)"""
        converted = {}
        for k, v in usernames.items():
            if isinstance(v, dict):
                converted[k] = v
            else:
                converted[k] = {"used": v, "followed_by": "", "followed_at": ""}
        return self._save_all(converted)

    def exists(self, username):
        """Check if a username is already in the tracker"""
        try:
            resp = (supabase.table(TABLE)
                    .select("username")
                    .eq("username", username)
                    .execute())
            return len(resp.data) > 0
        except Exception as e:
            print(f"❌ Error checking existence: {e}")
            return False

    def mark_as_used(self, username, followed_by=""):
        """Mark a username as followed by a specific account"""
        now = datetime.now().isoformat()
        try:
            # Upsert: creates if missing, updates if exists
            supabase.table(TABLE).upsert({
                "username": username,
                "used": True,
                "followed_by": followed_by,
                "followed_at": now,
            }).execute()
            print(f"✓ Marked '{username}' as followed by @{followed_by}")
            return True
        except Exception as e:
            print(f"❌ Error marking as used: {e}")
            return False

    def mark_as_unused(self, username):
        """Mark a username as unused (reset)"""
        if not self.exists(username):
            print(f"⚠️ Username '{username}' not found in tracker!")
            return False

        try:
            (supabase.table(TABLE)
             .update({"used": False, "followed_by": "", "followed_at": None})
             .eq("username", username)
             .execute())
            print(f"✓ Marked '{username}' as unused")
            return True
        except Exception as e:
            print(f"❌ Error marking as unused: {e}")
            return False

    def get_unused_usernames(self, limit=None):
        """Get list of unused usernames"""
        try:
            query = (supabase.table(TABLE)
                     .select("username")
                     .eq("used", False)
                     .order("username"))
            if limit:
                query = query.limit(limit)
            resp = query.execute()
            return [row["username"] for row in resp.data]
        except Exception as e:
            print(f"❌ Error getting unused usernames: {e}")
            return []

    def get_next_unused(self):
        """Get the first unused username"""
        unused = self.get_unused_usernames(limit=1)
        return unused[0] if unused else None

    def get_status(self, username=None):
        """Get status of usernames"""
        if username:
            try:
                resp = (supabase.table(TABLE)
                        .select("*")
                        .eq("username", username)
                        .execute())
                if resp.data:
                    row = resp.data[0]
                    if row["used"]:
                        status = f"✓ FOLLOWED by @{row['followed_by']} at {row['followed_at']}"
                    else:
                        status = "⚟ UNUSED"
                    print(f"Username: '{username}' -> {status}")
                    return row["used"]
                else:
                    print(f"⚠️ Username '{username}' not found!")
                    return None
            except Exception as e:
                print(f"❌ Error getting status: {e}")
                return None
        else:
            try:
                all_resp = supabase.table(TABLE).select("used").execute()
                total = len(all_resp.data)
                used = sum(1 for r in all_resp.data if r["used"])
                unused = total - used

                print(f"\n{'='*50}")
                print(f"Tracker Stats:")
                print(f"{'='*50}")
                print(f"Total usernames: {total}")
                print(f"Followed: {used}")
                print(f"Unused: {unused}")
                print(f"{'='*50}\n")

                return {'total': total, 'used': used, 'unused': unused}
            except Exception as e:
                print(f"❌ Error getting status: {e}")
                return {'total': 0, 'used': 0, 'unused': 0}

    def add_username(self, username):
        """Add a new username to tracker (skip if exists)"""
        if self.exists(username):
            return False  # Already exists, skip silently

        try:
            supabase.table(TABLE).insert({
                "username": username,
                "used": False,
                "followed_by": "",
                "followed_at": None,
            }).execute()
            return True
        except Exception as e:
            print(f"❌ Error adding username: {e}")
            return False

    def add_usernames_bulk(self, username_list):
        """Add multiple usernames, skipping duplicates. Returns count of new adds."""
        if not username_list:
            return 0

        try:
            # Get existing usernames in one query
            existing_resp = (supabase.table(TABLE)
                             .select("username")
                             .in_("username", list(username_list))
                             .execute())
            existing = {r["username"] for r in existing_resp.data}

            new_rows = []
            for uname in username_list:
                if uname not in existing:
                    new_rows.append({
                        "username": uname,
                        "used": False,
                        "followed_by": "",
                        "followed_at": None,
                    })

            if new_rows:
                supabase.table(TABLE).insert(new_rows).execute()
            return len(new_rows)
        except Exception as e:
            print(f"❌ Error bulk adding usernames: {e}")
            return 0

    def remove_username(self, username):
        """Remove a username from tracker"""
        if not self.exists(username):
            print(f"⚠️ Username '{username}' not found!")
            return False

        try:
            supabase.table(TABLE).delete().eq("username", username).execute()
            print(f"✓ Removed '{username}' from tracker")
            return True
        except Exception as e:
            print(f"❌ Error removing username: {e}")
            return False


if __name__ == "__main__":
    tracker = UsernameTracker()
    tracker.get_status()
