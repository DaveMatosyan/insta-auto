"""
Follow ramp-up logic — progressive daily limits based on lifetime follows.

Ramp schedule (per account):
    Phase 1:   0 – 69   total follows → 10/day
    Phase 2:  70 – 209  total follows → 20/day
    Phase 3: 210 – 419  total follows → 30/day
    Phase 4: 420 – 699  total follows → 40/day
    Phase 5: 700+       total follows → 50/day
"""

from datetime import date, datetime, timezone

from db.supabase_client import supabase

# ── Ramp schedule ──────────────────────────────────────────────
# Each tuple: (min_total_follows, daily_limit)
RAMP_SCHEDULE = [
    (700, 50),
    (420, 40),
    (210, 30),
    (70,  20),
    (0,   10),
]


def get_phase(total_follows: int) -> int:
    """Return the current phase number (1-5) based on total lifetime follows."""
    if total_follows >= 700:
        return 5
    elif total_follows >= 420:
        return 4
    elif total_follows >= 210:
        return 3
    elif total_follows >= 70:
        return 2
    else:
        return 1


def get_daily_limit(total_follows: int) -> int:
    """Return the daily follow limit for an account with `total_follows` lifetime follows."""
    for threshold, limit in RAMP_SCHEDULE:
        if total_follows >= threshold:
            return limit
    return 10  # fallback


def get_phase_info(total_follows: int) -> dict:
    """Return phase number, daily limit, and progress through the current phase."""
    phase = get_phase(total_follows)
    daily_limit = get_daily_limit(total_follows)

    phase_ranges = {
        1: (0, 70),
        2: (70, 210),
        3: (210, 420),
        4: (420, 700),
        5: (700, None),  # open-ended
    }

    start, end = phase_ranges[phase]
    if end is not None:
        progress = total_follows - start
        phase_size = end - start
    else:
        progress = total_follows - start
        phase_size = None  # ongoing

    return {
        "phase": phase,
        "daily_limit": daily_limit,
        "phase_start": start,
        "phase_end": end,
        "progress_in_phase": progress,
        "phase_size": phase_size,
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
    Query Supabase for the account's total_follows and daily_follows_today.
    Returns how many more follows this account can do today.
    """
    resp = supabase.table("accounts") \
        .select("total_follows, daily_follows_today, status") \
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

    daily_limit = get_daily_limit(row["total_follows"])
    done_today = row["daily_follows_today"] or 0
    remaining = max(0, daily_limit - done_today)

    return remaining


def get_all_active_accounts() -> list[dict]:
    """
    Fetch all active accounts from Supabase with their ramp info.
    Returns list of dicts with username, total_follows, daily_follows_today,
    daily_limit, remaining, and phase info.
    """
    resp = supabase.table("accounts") \
        .select("*") \
        .eq("status", "active") \
        .order("username") \
        .execute()

    accounts = []
    for row in resp.data:
        info = get_phase_info(row["total_follows"] or 0)
        daily_done = row["daily_follows_today"] or 0
        accounts.append({
            "username": row["username"],
            "email": row["email"],
            "total_follows": row["total_follows"] or 0,
            "daily_follows_today": daily_done,
            "daily_limit": info["daily_limit"],
            "remaining": max(0, info["daily_limit"] - daily_done),
            "phase": info["phase"],
            "phase_info": info,
            "last_follow_date": row["last_follow_date"],
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


