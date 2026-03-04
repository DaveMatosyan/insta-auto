"""
Proxy pool management — load, assign, test proxies
"""

import json
import os
import requests
from config import PROXIES_FILE, ACCOUNTS_PER_PROXY, JSON_FILE


def load_proxies():
    """Load proxy list from proxies.json"""
    if not os.path.exists(PROXIES_FILE):
        print(f"⚠️ {PROXIES_FILE} not found! Create it with your proxy list.")
        return []
    with open(PROXIES_FILE, 'r') as f:
        return json.load(f)


def _load_accounts():
    """Load accounts to check existing proxy assignments"""
    if not os.path.exists(JSON_FILE):
        return []
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def get_assigned_proxies():
    """Return set of proxy URLs already assigned to accounts"""
    accounts = _load_accounts()
    return {a.get("proxy_url") for a in accounts if a.get("proxy_url")}


def assign_proxy(username=None):
    """
    Pick the next available proxy (fewest assignments).

    Returns:
        str: proxy URL, or None if no proxies available
    """
    proxies = load_proxies()
    if not proxies:
        return None

    accounts = _load_accounts()
    # Count how many accounts use each proxy
    usage = {}
    for p in proxies:
        usage[p["url"]] = 0
    for a in accounts:
        purl = a.get("proxy_url")
        if purl and purl in usage:
            usage[purl] += 1

    # Find proxy with fewest assignments (respecting ACCOUNTS_PER_PROXY limit)
    for proxy in proxies:
        if usage.get(proxy["url"], 0) < ACCOUNTS_PER_PROXY:
            return proxy["url"]

    # All at capacity — return the least-used one anyway
    least_used = min(proxies, key=lambda p: usage.get(p["url"], 0))
    print(f"⚠️ All proxies at capacity ({ACCOUNTS_PER_PROXY}/proxy). Reusing {least_used['label']}")
    return least_used["url"]


def get_proxy(username):
    """Get the proxy URL bound to a specific account"""
    accounts = _load_accounts()
    for a in accounts:
        if a.get("username") == username:
            return a.get("proxy_url")
    return None


def test_proxy(proxy_url, timeout=10):
    """
    Test a proxy — verify connectivity and return external IP.

    Returns:
        str: External IP if successful, None on failure
    """
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=timeout)
        ip = r.json().get("ip")
        print(f"✅ Proxy OK → IP: {ip}  ({proxy_url[:40]}...)")
        return ip
    except Exception as e:
        print(f"❌ Proxy FAILED: {proxy_url[:40]}... → {e}")
        return None


def test_all_proxies():
    """Test all proxies and print results"""
    proxies = load_proxies()
    if not proxies:
        print("No proxies configured.")
        return

    print(f"\nTesting {len(proxies)} proxies...\n")
    results = []
    for p in proxies:
        ip = test_proxy(p["url"])
        results.append({"label": p["label"], "url": p["url"], "ip": ip, "ok": ip is not None})

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*50}")
    print(f"Results: {ok}/{len(results)} proxies working")
    print(f"{'='*50}")
    return results


if __name__ == "__main__":
    test_all_proxies()
