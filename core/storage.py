"""
Account storage — Supabase-backed operations for Instagram accounts.
"""

import json
from db.supabase_client import supabase


def _row_to_account(row):
    """Convert a Supabase row to the account dict format used everywhere."""
    acc = {
        "username": row["username"],
        "email": row.get("email", ""),
        "password": row.get("password", ""),
        "role": row.get("role", "follow"),
    }
    fp = row.get("fingerprint")
    if fp:
        acc["fingerprint"] = fp if isinstance(fp, dict) else json.loads(fp)
    if row.get("proxy_url"):
        acc["proxy_url"] = row["proxy_url"]
    return acc


def load_accounts():
    """Load all accounts from Supabase."""
    try:
        resp = supabase.table("accounts").select("*").execute()
        return [_row_to_account(r) for r in resp.data]
    except Exception as e:
        print(f"Error loading accounts from Supabase: {e}")
        return []


def save_account(email, username, password, fingerprint=None, proxy_url=None, role="follow"):
    """Save a new account to Supabase."""
    row = {
        "email": email,
        "username": username,
        "password": password,
        "role": role,
        "status": "active",
        "total_follows": 0,
        "daily_follows_today": 0,
    }
    if fingerprint:
        row["fingerprint"] = fingerprint
    if proxy_url:
        row["proxy_url"] = proxy_url

    try:
        supabase.table("accounts").insert(row).execute()
        print(f"Saved account @{username} to Supabase")
    except Exception as e:
        print(f"Error saving account @{username}: {e}")


def update_account(username, **fields):
    """Update any fields on an existing account."""
    try:
        resp = supabase.table("accounts").update(fields).eq("username", username).execute()
        if resp.data:
            print(f"Updated account '{username}': {list(fields.keys())}")
            return True
        print(f"Account '{username}' not found")
        return False
    except Exception as e:
        print(f"Error updating account '{username}': {e}")
        return False


def get_all_accounts(role=None):
    """Return accounts, optionally filtered by role."""
    try:
        query = supabase.table("accounts").select("*")
        if role:
            query = query.eq("role", role)
        resp = query.execute()
        accounts = [_row_to_account(r) for r in resp.data]
        if role and not accounts:
            print(f"Warning: no accounts with role='{role}', returning all accounts")
            return load_accounts()
        return accounts
    except Exception as e:
        print(f"Error fetching accounts: {e}")
        return []


def get_account_by_username(username):
    """Get account data by username."""
    try:
        resp = supabase.table("accounts").select("*").eq("username", username).limit(1).execute()
        if resp.data:
            return _row_to_account(resp.data[0])
    except Exception as e:
        print(f"Error fetching account @{username}: {e}")
    return None


def get_fingerprint_by_username(username):
    """Get browser fingerprint for a specific account."""
    account = get_account_by_username(username)
    if account:
        return account.get("fingerprint")
    return None


def get_account_count():
    """Get the number of saved accounts."""
    try:
        resp = supabase.table("accounts").select("username").execute()
        return len(resp.data)
    except Exception as e:
        print(f"Error counting accounts: {e}")
        return 0
