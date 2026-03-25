"""
Proxy manager — auto-rotating ProxyShare residential proxies.

ProxyShare rotation works by changing the session ID in the proxy URL.
Each session ID = a unique residential IP that lasts up to `life` minutes.
To get a new IP, generate a new random session ID.

Proxy URL format:
    http://{user_id}_area-{country}_city-{city}_session-{SESSION_ID}_life-{minutes}:{password}@{server}:{port}
"""

import json
import os
import random
import string
import time
from datetime import datetime, timedelta

import requests

from config import PROJECT_ROOT


# --- ProxyShare configuration ---
PROXYSHARE_CONFIG_FILE = os.path.join(PROJECT_ROOT, "proxyshare_config.json")

DEFAULT_CONFIG = {
    "user_id": "ps-Matos000",
    "password": "Killer621",
    "server": "proxy.proxyshare.com",
    "port": 5959,
    "area": "US",
    "city": "brent",
    "session_life_minutes": 120,
    "rotate_min_minutes": 40,
    "rotate_max_minutes": 100,
}

SESSIONS_FILE = os.path.join(PROJECT_ROOT, "proxy_sessions.json")


def _load_config():
    """Load ProxyShare config from file, or create default."""
    if os.path.exists(PROXYSHARE_CONFIG_FILE):
        with open(PROXYSHARE_CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
    else:
        with open(PROXYSHARE_CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Created {PROXYSHARE_CONFIG_FILE} with default settings")
        return DEFAULT_CONFIG


def _load_sessions():
    """Load active proxy sessions from file."""
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_sessions(sessions):
    """Save proxy sessions to file."""
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)


def _generate_session_id(length=10):
    """Generate a random session ID for ProxyShare."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


def _build_proxy_url(config, session_id):
    """Build a full ProxyShare proxy URL with the given session ID."""
    username = (
        f"{config['user_id']}"
        f"_area-{config['area']}"
        f"_city-{config['city']}"
        f"_session-{session_id}"
        f"_life-{config['session_life_minutes']}"
    )
    return f"http://{username}:{config['password']}@{config['server']}:{config['port']}"


def _random_rotate_time(config):
    """Pick a random rotation time between min and max minutes."""
    min_m = config.get('rotate_min_minutes', 40)
    max_m = config.get('rotate_max_minutes', 100)
    return random.randint(min_m, max_m)


def _is_session_expired(session_data, config):
    """Check if a proxy session needs rotation."""
    if not session_data:
        return True
    rotate_at = session_data.get('rotate_at')
    if not rotate_at:
        return True
    try:
        rotate_time = datetime.fromisoformat(rotate_at)
        return datetime.now() >= rotate_time
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_fresh_proxy(username=None):
    """
    Get a proxy URL for an account. Returns existing session if still valid,
    or creates a new one with a fresh IP.
    """
    config = _load_config()
    sessions = _load_sessions()

    key = username or "_default"
    current = sessions.get(key)

    if current and not _is_session_expired(current, config):
        proxy_url = _build_proxy_url(config, current['session_id'])
        remaining = ""
        try:
            rotate_at = datetime.fromisoformat(current['rotate_at'])
            mins_left = int((rotate_at - datetime.now()).total_seconds() / 60)
            remaining = f" ({mins_left}min left)"
        except:
            pass
        print(f"Reusing proxy session for @{username}{remaining}")
        return proxy_url

    new_session_id = _generate_session_id()
    rotate_in = _random_rotate_time(config)
    rotate_at = datetime.now() + timedelta(minutes=rotate_in)

    sessions[key] = {
        'session_id': new_session_id,
        'created_at': datetime.now().isoformat(),
        'rotate_at': rotate_at.isoformat(),
        'rotate_minutes': rotate_in,
    }
    _save_sessions(sessions)

    proxy_url = _build_proxy_url(config, new_session_id)
    action = "Rotated to new" if current else "Assigned new"
    print(f"{action} proxy for @{username} (session={new_session_id}, rotate in {rotate_in}min)")
    return proxy_url


def force_rotate(username=None):
    """Force-rotate to a new IP immediately for a specific account."""
    sessions = _load_sessions()
    key = username or "_default"
    sessions.pop(key, None)
    _save_sessions(sessions)
    print(f"Force-rotating proxy for @{username}...")
    return get_fresh_proxy(username)


def get_all_active_sessions():
    """Return all active proxy sessions with their status."""
    config = _load_config()
    sessions = _load_sessions()
    result = []
    for key, data in sessions.items():
        expired = _is_session_expired(data, config)
        remaining = ""
        if not expired:
            try:
                rotate_at = datetime.fromisoformat(data['rotate_at'])
                mins_left = int((rotate_at - datetime.now()).total_seconds() / 60)
                remaining = f"{mins_left}min"
            except:
                remaining = "?"
        result.append({
            'username': key,
            'session_id': data.get('session_id', '?'),
            'created_at': data.get('created_at', '?'),
            'expired': expired,
            'remaining': remaining,
        })
    return result


# Legacy compatibility
def assign_proxy(username=None):
    """Legacy: assign a proxy to an account (now auto-rotates)."""
    return get_fresh_proxy(username)


def get_proxy(username):
    """Legacy: get proxy for account."""
    return get_fresh_proxy(username)


def test_proxy(proxy_url, timeout=10):
    """Test a proxy — verify connectivity and return external IP."""
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=timeout)
        ip = r.json().get("ip")
        print(f"Proxy OK - IP: {ip}")
        return ip
    except Exception as e:
        print(f"Proxy FAILED: {e}")
        return None


def test_current_proxies():
    """Test all active proxy sessions."""
    config = _load_config()
    sessions = _load_sessions()

    if not sessions:
        print("No active proxy sessions. Generating a test proxy...")
        url = get_fresh_proxy("_test")
        test_proxy(url)
        return

    print(f"\nTesting {len(sessions)} active proxy sessions...\n")
    for key, data in sessions.items():
        sid = data.get('session_id', '?')
        url = _build_proxy_url(config, sid)
        expired = _is_session_expired(data, config)
        status = "EXPIRED" if expired else "ACTIVE"
        print(f"  @{key} [{status}] session={sid}")
        test_proxy(url)
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_current_proxies()
    elif len(sys.argv) > 1 and sys.argv[1] == "rotate":
        username = sys.argv[2] if len(sys.argv) > 2 else "_test"
        url = force_rotate(username)
        print(f"  New proxy: {url[:60]}...")
        test_proxy(url)
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        sessions = get_all_active_sessions()
        if not sessions:
            print("No active proxy sessions.")
        else:
            print(f"\n{'='*60}")
            for s in sessions:
                status = "EXPIRED" if s['expired'] else f"ACTIVE ({s['remaining']})"
                print(f"  @{s['username']:20s} session={s['session_id']:12s} {status}")
            print(f"{'='*60}")
    else:
        print("Usage:")
        print("  python -m core.proxy test     -- test all active proxies")
        print("  python -m core.proxy rotate   -- force-rotate to new IP")
        print("  python -m core.proxy status   -- show active sessions")
