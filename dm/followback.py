"""
Follow-back detection via instagrapi API.
Gets our followers list in one API call, then cross-references with follow_log.
"""

import time
import random

from datetime import datetime, timezone, timedelta

from db.supabase_client import supabase
from config import DM_MIN_FOLLOWBACK_AGE_DAYS, DM_MAX_FOLLOWBACK_AGE_DAYS
from dm.storage import create_conversation, check_existing_conversation, get_target_profile


def get_recent_follow_targets(account_username):
    """
    Get targets we followed 1-7 days ago (configurable window).
    These are candidates for follow-back checking.

    Returns:
        list of target usernames
    """
    try:
        now = datetime.now(timezone.utc)
        min_date = (now - timedelta(days=DM_MAX_FOLLOWBACK_AGE_DAYS)).isoformat()
        max_date = (now - timedelta(days=DM_MIN_FOLLOWBACK_AGE_DAYS)).isoformat()

        resp = supabase.table("follow_log") \
            .select("target_username") \
            .eq("account_username", account_username) \
            .gte("followed_at", min_date) \
            .lte("followed_at", max_date) \
            .execute()

        return [r["target_username"] for r in resp.data] if resp.data else []

    except Exception as e:
        print(f"  [followback] Error fetching recent targets for @{account_username}: {e}")
        return []


def detect_followbacks(client, account_username, max_checks=50):
    """
    Detect which targets followed us back using the API.
    Gets our full followers list in 1 call, then cross-references.

    Args:
        client: instagrapi Client (logged in)
        account_username: our account username
        max_checks: max new follow-backs to process

    Returns:
        list of usernames who followed back
    """
    targets = get_recent_follow_targets(account_username)

    if not targets:
        print(f"  [followback] No recent targets to check for @{account_username}")
        return []

    # Filter out targets we already have conversations with
    new_targets = []
    for t in targets:
        existing = check_existing_conversation(account_username, t)
        if not existing:
            new_targets.append(t)

    if not new_targets:
        print(f"  [followback] All {len(targets)} targets already have conversations")
        return []

    # Get our followers list in one API call
    print(f"  [followback] Fetching followers for @{account_username}...")
    try:
        our_user_id = client.user_id_from_username(account_username)
        followers = client.user_followers(our_user_id)
        follower_usernames = {u.username for u in followers.values()}
        print(f"  [followback] @{account_username} has {len(follower_usernames)} followers")
    except Exception as e:
        print(f"  [followback] Error fetching followers: {e}")
        return []

    # Cross-reference: which targets are in our followers?
    to_check = new_targets[:max_checks]
    followbacks = []

    for target in to_check:
        if target in follower_usernames:
            print(f"  [followback] + @{target} followed back!")
            followbacks.append(target)

            # Get their score from targets_scored
            profile = get_target_profile(target)
            score = profile.get("score")

            # Create pending conversation
            create_conversation(account_username, target, target_score=score)

    not_followed = len(to_check) - len(followbacks)
    print(f"  [followback] {len(followbacks)} follow-backs, {not_followed} not yet")
    return followbacks
