"""
Proxy manager — Supabase-backed static dedicated proxies.

Each proxy supports up to max_accounts (default 3) Instagram accounts.
Proxies are stored in the `proxies` table with a generated `proxy_url` column.
Accounts link to proxies via `proxy_id` FK.
"""

import requests

from db.supabase_client import supabase
from config import ACCOUNTS_PER_PROXY


def add_proxy(raw_string):
    """
    Add a proxy from 'host:port:user:pass' format.

    Returns:
        dict: the inserted proxy row, or None on error
    """
    parts = raw_string.strip().split(":")
    if len(parts) != 4:
        print(f"Invalid proxy format: {raw_string}")
        print("Expected: host:port:user:pass")
        return None

    host, port, username, password = parts
    try:
        row = {
            "host": host,
            "port": int(port),
            "username": username,
            "password": password,
            "max_accounts": ACCOUNTS_PER_PROXY,
        }
        resp = supabase.table("proxies").insert(row).execute()
        if resp.data:
            proxy = resp.data[0]
            print(f"Added proxy: {proxy['proxy_url']}")
            return proxy
    except Exception as e:
        print(f"Error adding proxy: {e}")
    return None


def get_available_proxy():
    """
    Find a proxy with fewer than max_accounts linked accounts.
    Used during account creation before the account row exists.

    Returns:
        str: proxy_url, or None if all proxies are full
    """
    try:
        proxies = supabase.table("proxies").select("*").eq("is_active", True).execute().data
        for proxy in proxies:
            count = supabase.table("accounts").select("username", count="exact").eq("proxy_id", proxy["id"]).execute().count
            if count < proxy.get("max_accounts", ACCOUNTS_PER_PROXY):
                return proxy["proxy_url"]
        print("All proxies are at capacity!")
        return None
    except Exception as e:
        print(f"Error finding available proxy: {e}")
        return None


def assign_proxy_to_account(username):
    """
    Find an available proxy and set proxy_id on the account row.

    Returns:
        str: proxy_url assigned, or None on failure
    """
    try:
        proxies = supabase.table("proxies").select("*").eq("is_active", True).execute().data
        for proxy in proxies:
            count = supabase.table("accounts").select("username", count="exact").eq("proxy_id", proxy["id"]).execute().count
            if count < proxy.get("max_accounts", ACCOUNTS_PER_PROXY):
                supabase.table("accounts").update({"proxy_id": proxy["id"]}).eq("username", username).execute()
                print(f"Assigned proxy {proxy['host']}:{proxy['port']} to @{username}")
                return proxy["proxy_url"]
        print(f"No available proxy for @{username} — all at capacity!")
        return None
    except Exception as e:
        print(f"Error assigning proxy to @{username}: {e}")
        return None


def get_proxy_for_account(username):
    """
    Get the proxy URL linked to an account via proxy_id FK.

    Returns:
        str: proxy_url, or None if no proxy assigned
    """
    try:
        resp = supabase.table("accounts").select("proxy_id, proxies(proxy_url)").eq("username", username).limit(1).execute()
        if resp.data and resp.data[0].get("proxies"):
            return resp.data[0]["proxies"]["proxy_url"]
        return None
    except Exception as e:
        print(f"Error getting proxy for @{username}: {e}")
        return None


def list_proxies():
    """List all proxies with their account counts."""
    try:
        proxies = supabase.table("proxies").select("*").execute().data
        print(f"\n{'='*60}")
        print(f"PROXIES ({len(proxies)} total)")
        print(f"{'='*60}")
        for proxy in proxies:
            count = supabase.table("accounts").select("username", count="exact").eq("proxy_id", proxy["id"]).execute().count
            status = "ACTIVE" if proxy["is_active"] else "INACTIVE"
            print(f"  {proxy['host']}:{proxy['port']} [{status}] "
                  f"accounts: {count}/{proxy.get('max_accounts', ACCOUNTS_PER_PROXY)}")
            # List linked accounts
            accs = supabase.table("accounts").select("username").eq("proxy_id", proxy["id"]).execute().data
            for a in accs:
                print(f"    -> @{a['username']}")
        print(f"{'='*60}\n")
        return proxies
    except Exception as e:
        print(f"Error listing proxies: {e}")
        return []


def test_proxy(proxy_url=None, timeout=10):
    """Test proxy connectivity and return external IP."""
    if not proxy_url:
        print("No proxy URL provided")
        return None
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=timeout)
        ip = r.json().get("ip")
        print(f"Proxy OK - IP: {ip}")
        return ip
    except Exception as e:
        print(f"Proxy FAILED: {e}")
        return None


# Legacy shims — keep imports working across codebase
def get_fresh_proxy(username=None):
    """Legacy: returns proxy for account."""
    if username:
        return get_proxy_for_account(username)
    return get_available_proxy()


def assign_proxy(username=None):
    """Legacy alias."""
    return get_fresh_proxy(username)


def get_proxy(username=None):
    """Legacy alias."""
    return get_fresh_proxy(username)


def force_rotate(username=None):
    """No rotation — static proxies. Returns available proxy for new accounts."""
    return get_available_proxy()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_proxies()
    elif len(sys.argv) > 1 and sys.argv[1] == "add":
        if len(sys.argv) < 3:
            print("Usage: python -m core.proxy add host:port:user:pass")
        else:
            add_proxy(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        proxies = supabase.table("proxies").select("*").eq("is_active", True).execute().data
        for p in proxies:
            print(f"\nTesting {p['host']}:{p['port']}...")
            test_proxy(p["proxy_url"])
    else:
        print("Usage:")
        print("  python -m core.proxy list           -- list all proxies + accounts")
        print("  python -m core.proxy add host:port:user:pass  -- add a proxy")
        print("  python -m core.proxy test            -- test all active proxies")
