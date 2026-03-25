"""
Follow ramp-up logic — progressive daily limits based on account age (days since created).

Ramp schedule (per account):
    Days  1-5:   5/day
    Days  6-10: 10/day
    Days 11-15: 20/day
    Days 16-20: 30/day
    Days 21+:   50/day
"""

from datetime import date, datetime, timezone

from db.supabase_client import supabase

# ── Ramp schedule ──────────────────────────────────────────────
# Each tuple: (min_days_since_created, daily_limit)
# Checked top-down, first match wins
RAMP_SCHEDULE = [
    (21, 50),
    (16, 30),
    (11, 20),
    (6,  10),
    (0,   5),
]


def _account_age_days(created_at) -> int:
    """Return number of days since the account was added to Supabase."""
    if not created_at:
        return 0
    if isinstance(created_at, str):
        # Parse ISO format from Supabase
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (now - created_at).days


def get_phase(age_days: int) -> int:
    """Return the current phase number (1-5) based on account age in days."""
    if age_days >= 21:
        return 5
    elif age_days >= 16:
        return 4
    elif age_days >= 11:
        return 3
    elif age_days >= 6:
        return 2
    else:
        return 1


def get_daily_limit(age_days: int) -> int:
    """Return the daily follow limit based on account age in days."""
    for threshold, limit in RAMP_SCHEDULE:
        if age_days >= threshold:
            return limit
    return 5  # fallback


def get_phase_info(age_days: int) -> dict:
    """Return phase number, daily limit, and progress info."""
    phase = get_phase(age_days)
    daily_limit = get_daily_limit(age_days)

    phase_ranges = {
        1: (0, 5),
        2: (6, 10),
        3: (11, 15),
        4: (16, 20),
        5: (21, None),
    }

    start, end = phase_ranges[phase]

    return {
        "phase": phase,
        "daily_limit": daily_limit,
        "phase_start_day": start,
        "phase_end_day": end,
        "account_age_days": age_days,
    }


# ── Account queries ───────────────────────────────────────────

def reset_daily_counts():
    """
    Reset `daily_follows_today` to 0 for all accounts whose
    `last_follow_date` is before today (or NULL).
    Called once at the start of each day's run.
    """
    today = date.today().isoformat()

    # Reset accounts whose last_follow_date is not today
    supabase.table("accounts") \
        .update({"daily_follows_today": 0}) \
        .neq("last_follow_date", today) \
        .execute()

    # Also reset accounts with NULL last_follow_date
    supabase.table("accounts") \
        .update({"daily_follows_today": 0}) \
        .is_("last_follow_date", "null") \
        .execute()

    print(f"[ramp] Daily counts reset for {today}")


def get_account_allowance(username: str) -> int:
    """
    Query Supabase for the account's age and daily_follows_today.
    Returns how many more follows this account can do today.
    """
    resp = supabase.table("accounts") \
        .select("total_follows, daily_follows_today, status, created_at") \
        .eq("username", username) \
        .single() \
        .execute()

    row = resp.data
    if not row:
        print(f"[ramp] Account @{username} not found in Supabase")
        return 0

    if row["status"] != "active":
        print(f"[ramp] Account @{username} is {row['status']}, skipping")
        return 0

    age_days = _account_age_days(row.get("created_at"))
    daily_limit = get_daily_limit(age_days)
    done_today = row["daily_follows_today"] or 0
    remaining = max(0, daily_limit - done_today)

    return remaining


def get_all_active_accounts() -> list[dict]:
    """
    Fetch all active non-scraper accounts from Supabase with their ramp info.
    """
    resp = supabase.table("accounts") \
        .select("*") \
        .eq("status", "active") \
        .neq("role", "scraper") \
        .order("username") \
        .execute()

    accounts = []
    for row in resp.data:
        age_days = _account_age_days(row.get("created_at"))
        info = get_phase_info(age_days)
        daily_done = row["daily_follows_today"] or 0
        accounts.append({
            "username": row["username"],
            "email": row.get("email", ""),
            "total_follows": row["total_follows"] or 0,
            "daily_follows_today": daily_done,
            "daily_limit": info["daily_limit"],
            "remaining": max(0, info["daily_limit"] - daily_done),
            "phase": info["phase"],
            "phase_info": info,
            "account_age_days": age_days,
            "last_follow_date": row.get("last_follow_date"),
            "status": row["status"],
        })

    return accounts


# ── Follow recording ─────────────────────────────────────────

def record_follow(account_username: str, target_username: str):
    """
    Record a successful follow:
    1. Insert into follow_log
    2. Increment total_follows and daily_follows_today on accounts table
    3. Update last_follow_date to today
    """
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    # 1. Insert into follow_log
    supabase.table("follow_log").insert({
        "account_username": account_username,
        "target_username": target_username,
        "followed_at": now,
    }).execute()

    # 2. Get current counts
    resp = supabase.table("accounts") \
        .select("total_follows, daily_follows_today") \
        .eq("username", account_username) \
        .single() \
        .execute()

    row = resp.data
    new_total = (row["total_follows"] or 0) + 1
    new_daily = (row["daily_follows_today"] or 0) + 1

    # 3. Update account
    supabase.table("accounts").update({
        "total_follows": new_total,
        "daily_follows_today": new_daily,
        "last_follow_date": today,
    }).eq("username", account_username).execute()


