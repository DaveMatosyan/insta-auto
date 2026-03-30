"""
DM rate limiting — weekly ramp-up based on account's dm_start_date.

Ramp schedule:
    Week 1 (days 0-6):   5 DMs/day
    Week 2 (days 7-13):  10 DMs/day
    Week 3 (days 14-20): 20 DMs/day
    Week 4+ (days 21+):  40 DMs/day
"""

from datetime import date, datetime, timezone

from db.supabase_client import supabase
from config import DM_RAMP_SCHEDULE


def get_dm_daily_limit(account_row):
    """
    Calculate today's DM limit based on days since dm_start_date.

    Args:
        account_row: dict with dm_start_date field

    Returns:
        int: daily DM limit
    """
    dm_start = account_row.get("dm_start_date")
    if not dm_start:
        return DM_RAMP_SCHEDULE[0][1]  # Default to week 1 limit

    if isinstance(dm_start, str):
        dm_start = date.fromisoformat(dm_start)

    days_active = (date.today() - dm_start).days

    # Find the right limit from ramp schedule (sorted ascending by day threshold)
    limit = DM_RAMP_SCHEDULE[0][1]
    for day_threshold, daily_limit in DM_RAMP_SCHEDULE:
        if days_active >= day_threshold:
            limit = daily_limit

    return limit


def get_dm_week(account_row):
    """Return which week the account is in (1-4+)."""
    dm_start = account_row.get("dm_start_date")
    if not dm_start:
        return 1
    if isinstance(dm_start, str):
        dm_start = date.fromisoformat(dm_start)
    days = (date.today() - dm_start).days
    return min(days // 7 + 1, 4)


def reset_daily_dm_counts():
    """
    Reset daily_dms_sent to 0 for accounts whose last_dm_date is not today.
    Called at the start of each DM run.
    """
    today = date.today().isoformat()

    supabase.table("accounts") \
        .update({"daily_dms_sent": 0}) \
        .neq("last_dm_date", today) \
        .execute()

    supabase.table("accounts") \
        .update({"daily_dms_sent": 0}) \
        .is_("last_dm_date", "null") \
        .execute()

    print(f"[dm-ramp] Daily DM counts reset for {today}")


def get_dm_allowance(username):
    """
    Get how many more DMs this account can send today.

    Returns:
        int: remaining DM allowance
    """
    try:
        resp = supabase.table("accounts") \
            .select("total_dms_sent, daily_dms_sent, last_dm_date, dm_start_date, status") \
            .eq("username", username) \
            .single() \
            .execute()

        row = resp.data
        if not row or row.get("status") != "active":
            return 0

        daily_limit = get_dm_daily_limit(row)
        done_today = row.get("daily_dms_sent") or 0
        return max(0, daily_limit - done_today)

    except Exception as e:
        print(f"[dm-ramp] Error getting DM allowance for @{username}: {e}")
        return 0


def get_all_dm_accounts():
    """
    Fetch all active accounts with DM ramp info.

    Returns:
        list of dicts with username, dm daily limit, remaining, week info
    """
    try:
        resp = supabase.table("accounts") \
            .select("*") \
            .eq("status", "active") \
            .neq("role", "scraper") \
            .order("username") \
            .execute()

        accounts = []
        for row in resp.data:
            daily_limit = get_dm_daily_limit(row)
            done_today = row.get("daily_dms_sent") or 0
            accounts.append({
                "username": row["username"],
                "email": row.get("email", ""),
                "total_dms_sent": row.get("total_dms_sent") or 0,
                "daily_dms_sent": done_today,
                "dm_daily_limit": daily_limit,
                "dm_remaining": max(0, daily_limit - done_today),
                "dm_week": get_dm_week(row),
                "dm_start_date": row.get("dm_start_date"),
                "status": row.get("status"),
            })

        return accounts

    except Exception as e:
        print(f"[dm-ramp] Error fetching DM accounts: {e}")
        return []


def record_dm_sent(account_username):
    """
    Increment DM counters after sending a message.
    Also sets dm_start_date if this is the account's first DM.
    """
    today = date.today().isoformat()

    try:
        resp = supabase.table("accounts") \
            .select("total_dms_sent, daily_dms_sent, dm_start_date") \
            .eq("username", account_username) \
            .single() \
            .execute()

        row = resp.data
        updates = {
            "total_dms_sent": (row.get("total_dms_sent") or 0) + 1,
            "daily_dms_sent": (row.get("daily_dms_sent") or 0) + 1,
            "last_dm_date": today,
        }

        # Set dm_start_date on first DM
        if not row.get("dm_start_date"):
            updates["dm_start_date"] = today

        supabase.table("accounts") \
            .update(updates) \
            .eq("username", account_username) \
            .execute()

    except Exception as e:
        print(f"[dm-ramp] Error recording DM for @{account_username}: {e}")
