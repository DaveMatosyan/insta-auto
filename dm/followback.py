"""
Follow-back detection via Playwright browser.
Visits each target's profile and checks for "Follows you" badge.
"""

import time
import random

from datetime import datetime, timezone, timedelta

from db.supabase_client import supabase
from config import DM_MIN_FOLLOWBACK_AGE_DAYS, DM_MAX_FOLLOWBACK_AGE_DAYS
from dm.storage import create_conversation, check_existing_conversation, get_target_profile
from core.browser_follow import check_is_following_us


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


def detect_followbacks(page, account_username, max_checks=50):
    """
    Detect which targets followed us back by visiting their profiles.

    Args:
        page: Playwright Page (logged in)
        account_username: our account username
        max_checks: max targets to check

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

    to_check = new_targets[:max_checks]
    followbacks = []

    print(f"  [followback] Checking {len(to_check)} targets for follow-backs...")

    for target in to_check:
        if check_is_following_us(page, target):
            print(f"  [followback] + @{target} followed back!")
            followbacks.append(target)

            # Get their score from targets_scored
            profile = get_target_profile(target)
            score = profile.get("score")

            # Create pending conversation
            create_conversation(account_username, target, target_score=score)

        # Human-like delay between profile visits
        time.sleep(random.uniform(2, 5))

    not_followed = len(to_check) - len(followbacks)
    print(f"  [followback] {len(followbacks)} follow-backs, {not_followed} not yet")
    return followbacks
