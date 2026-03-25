"""
Shared utility functions — consolidated from the old root-level utils.py
plus duplicated helpers (human_delay, pick_best_account).
"""

import os
import random
import string
import subprocess
import time
from urllib.parse import urlparse

from config import SESSIONS_DIR


def human_delay(min_sec=1, max_sec=3):
    """Add random human-like delays between actions."""
    time.sleep(random.uniform(min_sec, max_sec))


def generate_random_string(length=8):
    """Generate a random string with lowercase letters and digits."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def get_current_ip():
    """Get current IP address to verify VPN connection."""
    try:
        services = [
            "curl -s ifconfig.me",
            "curl -s icanhazip.com",
            "curl -s api.ipify.org"
        ]
        for service in services:
            try:
                result = subprocess.run(service, shell=True, capture_output=True, text=True, timeout=10)
                ip = result.stdout.strip()
                if ip and '.' in ip:
                    print(f"Current IP: {ip}")
                    return ip
            except:
                continue
        print("Could not retrieve IP from any service")
        return None
    except Exception as e:
        print(f"Could not get IP: {e}")
        return None


def print_section_header(text):
    """Print a formatted section header."""
    print("\n" + "="*60)
    print(text)
    print("="*60 + "\n")


def print_account_info(email, username, password, fullname):
    """Print account creation information."""
    print(f"\n{'='*60}")
    print("ACCOUNT CREATION COMPLETE!")
    print(f"{'='*60}")
    print(f"EMAIL: {email}")
    print(f"USERNAME: {username}")
    print(f"PASSWORD: {password}")
    print(f"FULL NAME: {fullname}")
    print(f"{'='*60}\n")


def generate_browser_fingerprint():
    """
    Generate a random browser fingerprint for authentication.
    Includes user agent, headers, and browser characteristics.
    """
    iphone_user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    ]

    languages = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.8",
        "en;q=0.9,en-US;q=0.8",
    ]

    screen_resolutions = [
        {"width": 390, "height": 844},
        {"width": 430, "height": 932},
        {"width": 375, "height": 667},
        {"width": 414, "height": 896},
    ]

    webgl_vendors = [
        {"vendor": "Apple Inc.", "renderer": "Apple A16 Bionic GPU"},
        {"vendor": "Apple Inc.", "renderer": "Apple A15 Bionic GPU"},
        {"vendor": "Apple Inc.", "renderer": "Apple A14 Bionic GPU"},
    ]

    fingerprint = {
        "user_agent": random.choice(iphone_user_agents),
        "accept_language": random.choice(languages),
        "screen": random.choice(screen_resolutions),
        "webgl": random.choice(webgl_vendors),
        "timezone": "America/Los_Angeles",
        "platform": "iPhone",
        "device_model": random.choice(["iPhone 13", "iPhone 14", "iPhone 15", "iPhone 14 Pro", "iPhone 15 Pro"]),
        "generated_timestamp": time.time()
    }
    return fingerprint


def parse_proxy_url(proxy_url):
    """
    Parse a proxy URL into Playwright's proxy dict format.

    Input:  "http://user:pass@host:port"
    Output: {"server": "http://host:port", "username": "user", "password": "pass"}
    """
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    proxy_dict = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        proxy_dict["username"] = parsed.username
    if parsed.password:
        proxy_dict["password"] = parsed.password
    return proxy_dict


def pick_best_account(accounts, role=None):
    """
    Pick the best account — prefers accounts with large valid cookies.

    Args:
        accounts: list of account dicts
        role: optional role filter (e.g. "scraper", "follow")

    Returns:
        dict: best account, or first matching as fallback
    """
    pool = accounts
    if role:
        filtered = [a for a in accounts if a.get("role") == role]
        if filtered:
            pool = filtered

    for acc in reversed(pool):
        cookie_file = os.path.join(SESSIONS_DIR, f"{acc['username']}_state.json")
        if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 5000:
            print(f"Using account @{acc['username']} (role={acc.get('role','none')}, has cookies)")
            return acc
    fallback = pool[0]
    print(f"No account with valid cookies, using @{fallback['username']} (role={fallback.get('role','none')})")
    return fallback
