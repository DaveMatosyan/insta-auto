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


# ── Unified device profiles: one identity for browser + instagrapi API ──
# Each profile contains BOTH the instagrapi fields AND the matching browser
# fingerprint data so the same device appears across creation and daily use.
DEVICE_PROFILES = [
    # Samsung Galaxy S23 Ultra — Exynos 2200
    {
        "manufacturer": "samsung", "model": "SM-S918B",
        "android_version": 34, "android_release": "14",
        "dpi": "480dpi", "resolution": "1080x2340",
        "cpu": "exynos2200", "version_code": "314665256",
        "chrome_version": "131.0.6778.39",
        "screen_width": 384, "screen_height": 824,
        "device_scale_factor": 2.8125,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G78 MP14",
    },
    # Samsung Galaxy S21 Ultra — Exynos 2100
    {
        "manufacturer": "samsung", "model": "SM-G998B",
        "android_version": 33, "android_release": "13",
        "dpi": "640dpi", "resolution": "1440x3200",
        "cpu": "exynos2100", "version_code": "314665256",
        "chrome_version": "130.0.6723.102",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 3.5,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G78 MP14",
    },
    # Samsung Galaxy A54 — Exynos 1380
    {
        "manufacturer": "samsung", "model": "SM-A546B",
        "android_version": 34, "android_release": "14",
        "dpi": "400dpi", "resolution": "1080x2400",
        "cpu": "exynos1380", "version_code": "314665256",
        "chrome_version": "131.0.6778.39",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G68 MC4",
    },
    # Samsung Galaxy S23+ — Exynos 2200
    {
        "manufacturer": "samsung", "model": "SM-S916B",
        "android_version": 34, "android_release": "14",
        "dpi": "480dpi", "resolution": "1080x2340",
        "cpu": "exynos2200", "version_code": "314665256",
        "chrome_version": "129.0.6668.81",
        "screen_width": 384, "screen_height": 824,
        "device_scale_factor": 2.8125,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G78 MP14",
    },
    # Google Pixel 8 Pro — Tensor G3
    {
        "manufacturer": "Google", "model": "Pixel 8 Pro",
        "android_version": 34, "android_release": "14",
        "dpi": "480dpi", "resolution": "1344x2992",
        "cpu": "tensor_g3", "version_code": "314665256",
        "chrome_version": "131.0.6778.39",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G715 MC7",
    },
    # Google Pixel 7 — Tensor G2
    {
        "manufacturer": "Google", "model": "Pixel 7",
        "android_version": 34, "android_release": "14",
        "dpi": "420dpi", "resolution": "1080x2400",
        "cpu": "tensor_g2", "version_code": "314665256",
        "chrome_version": "130.0.6723.102",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G710 MC10",
    },
    # Google Pixel 8a — Tensor G3
    {
        "manufacturer": "Google", "model": "Pixel 8a",
        "android_version": 34, "android_release": "14",
        "dpi": "420dpi", "resolution": "1080x2400",
        "cpu": "tensor_g3", "version_code": "314665256",
        "chrome_version": "131.0.6778.39",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "ARM", "webgl_renderer": "Mali-G715 MC7",
    },
    # OnePlus 11 — Snapdragon 8 Gen 2
    {
        "manufacturer": "OnePlus", "model": "CPH2449",
        "android_version": 34, "android_release": "14",
        "dpi": "480dpi", "resolution": "1240x2772",
        "cpu": "qcom", "version_code": "314665256",
        "chrome_version": "129.0.6668.81",
        "screen_width": 412, "screen_height": 919,
        "device_scale_factor": 3.0,
        "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 740",
    },
    # OnePlus 10 Pro — Snapdragon 8 Gen 1
    {
        "manufacturer": "OnePlus", "model": "NE2215",
        "android_version": 33, "android_release": "13",
        "dpi": "480dpi", "resolution": "1080x2400",
        "cpu": "qcom", "version_code": "314665256",
        "chrome_version": "130.0.6723.102",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 730",
    },
    # Xiaomi 13 Pro — Snapdragon 8 Gen 2
    {
        "manufacturer": "Xiaomi", "model": "23049PCD8G",
        "android_version": 34, "android_release": "14",
        "dpi": "440dpi", "resolution": "1220x2712",
        "cpu": "qcom", "version_code": "314665256",
        "chrome_version": "131.0.6778.39",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.75,
        "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 740",
    },
    # Xiaomi 12 — Snapdragon 8 Gen 1
    {
        "manufacturer": "Xiaomi", "model": "2211133G",
        "android_version": 33, "android_release": "13",
        "dpi": "440dpi", "resolution": "1080x2400",
        "cpu": "qcom", "version_code": "314665256",
        "chrome_version": "129.0.6668.81",
        "screen_width": 393, "screen_height": 873,
        "device_scale_factor": 2.75,
        "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 730",
    },
    # Motorola Edge 40 Pro — Snapdragon 8 Gen 2
    {
        "manufacturer": "motorola", "model": "motorola edge 40 pro",
        "android_version": 34, "android_release": "14",
        "dpi": "400dpi", "resolution": "1080x2400",
        "cpu": "qcom", "version_code": "314665256",
        "chrome_version": "130.0.6723.102",
        "screen_width": 412, "screen_height": 915,
        "device_scale_factor": 2.625,
        "webgl_vendor": "Qualcomm", "webgl_renderer": "Adreno (TM) 740",
    },
]


def pick_device_profile():
    """Pick a random unified device profile."""
    return random.choice(DEVICE_PROFILES)


def generate_browser_fingerprint(device_profile=None):
    """
    Generate a browser fingerprint that matches the Android device profile
    used by instagrapi. This ensures Instagram sees the SAME device during
    browser account creation and later API usage.

    Args:
        device_profile: A dict from DEVICE_PROFILES. If None, picks random.

    Returns:
        dict with browser fingerprint fields + embedded device_profile.
    """
    if device_profile is None:
        device_profile = pick_device_profile()

    model = device_profile["model"]
    android_release = device_profile["android_release"]
    chrome_ver = device_profile["chrome_version"]

    user_agent = (
        f"Mozilla/5.0 (Linux; Android {android_release}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Mobile Safari/537.36"
    )

    languages = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.9,es;q=0.8",
        "en-US,en;q=0.8",
    ]

    timezones = [
        "America/Los_Angeles",
        "America/Denver",
        "America/Chicago",
        "America/New_York",
    ]

    fingerprint = {
        "user_agent": user_agent,
        "accept_language": random.choice(languages),
        "screen": {
            "width": device_profile["screen_width"],
            "height": device_profile["screen_height"],
        },
        "webgl": {
            "vendor": device_profile["webgl_vendor"],
            "renderer": device_profile["webgl_renderer"],
        },
        "timezone": random.choice(timezones),
        "platform": "Linux armv8l",
        "device_model": f"{device_profile['manufacturer']} {model}",
        "device_scale_factor": device_profile["device_scale_factor"],
        "device_profile": device_profile,
        "generated_timestamp": time.time(),
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
