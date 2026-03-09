"""
Supabase persistence — save scored targets and merge into tracker.
"""

import os

from config import PROJECT_ROOT
from db.supabase_client import supabase

RAW_COMMENTERS_TXT = os.path.join(PROJECT_ROOT, "raw_commenters.txt")
RAW_COMMENTERS_JSON = os.path.join(PROJECT_ROOT, "raw_commenters.json")

TARGETS_TABLE = "targets_scored"


def save_targets(targets):
    """Save scored targets to Supabase (upsert, deduplicates on username).

    Args:
        targets: list of dicts, each with at least a 'username' key

    Returns:
        int: number of new targets inserted
    """
    if not targets:
        return 0

    try:
        # Get existing usernames to count truly new ones
        usernames = [t["username"] for t in targets]
        existing_resp = (supabase.table(TARGETS_TABLE)
                         .select("username")
                         .in_("username", usernames)
                         .execute())
        existing = {r["username"] for r in existing_resp.data}

        # Upsert all (updates existing, inserts new)
        rows = []
        for t in targets:
            row = {
                "username": t["username"],
                "profile_url": t.get("profile_url", ""),
                "score": int(t.get("score", 0)),
                "followers": int(t.get("followers", 0)),
                "following": int(t.get("following", 0)),
                "follow_ratio": float(t.get("follow_ratio", 0)),
                "posts": int(t.get("posts", 0)),
                "fullname": t.get("fullname", ""),
                "bio": t.get("bio", ""),
                "external_link": t.get("external_link", ""),
                "is_private": bool(t.get("is_private", False)),
                "is_verified": bool(t.get("is_verified", False)),
                "has_story": bool(t.get("has_story", False)),
                "has_custom_pfp": bool(t.get("has_custom_pfp", False)),
                "gender": t.get("gender", "unknown"),
                "reasons": t.get("reasons", "")[:150],
                "source_creator": t.get("source_creator", ""),
                "source_post": t.get("source_post", ""),
                "comment": t.get("comment", "")[:100],
                "scraped_at": t.get("scraped_at"),
            }
            rows.append(row)

        supabase.table(TARGETS_TABLE).upsert(rows).execute()

        new_count = sum(1 for t in targets if t["username"] not in existing)
        total = len(existing) + new_count
        print(f"Saved {new_count} new targets to Supabase (total: {total})")
        return new_count
    except Exception as e:
        print(f"❌ Error saving targets to Supabase: {e}")
        return 0


# Keep old name as alias for backward compatibility
save_targets_csv = save_targets


def merge_to_tracker(targets, tracker_path=None):
    """Add scored targets to the main username tracker for daily follows."""
    from csv_management.username_manager import UsernameTracker
    tracker = UsernameTracker()
    usernames = [t['username'] for t in targets]
    new_count = tracker.add_usernames_bulk(usernames)
    total_resp = supabase.table("usernames_tracker").select("username", count="exact").execute()
    total = total_resp.count if total_resp.count is not None else len(total_resp.data)
    print(f"Merged {new_count} new targets into tracker (total: {total})")
