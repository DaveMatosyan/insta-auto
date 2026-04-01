"""
Shared instagrapi client manager — creates authenticated API clients for all modules.
Handles session persistence, proxy setup, device fingerprints, UUID preservation,
and challenge auto-resolution via Gmail.

Device identity: uses the SAME Android device profile that was assigned during
account creation (stored in the account's fingerprint.device_profile in Supabase).
This prevents Instagram from seeing a "device change" between browser and API.
"""

import os
import random
import time

from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, TwoFactorRequired

from config import SESSIONS_DIR
from core.proxy import get_fresh_proxy
from core.utils import DEVICE_PROFILES


# Session files stored in {SESSIONS_DIR}/api/
API_SESSIONS_DIR = os.path.join(SESSIONS_DIR, "api")


def _get_session_path(username):
    """Return path to API session file for an account."""
    os.makedirs(API_SESSIONS_DIR, exist_ok=True)
    return os.path.join(API_SESSIONS_DIR, f"{username}_api.json")


def _get_verification_code(email, wait_sec=10):
    """Get Instagram verification code from Gmail API."""
    time.sleep(wait_sec)
    try:
        from creator.gmail_api import (
            authenticate_gmail_api,
            build_gmail_service,
            get_verification_code_from_gmail_api,
        )
        creds = authenticate_gmail_api()
        service = build_gmail_service(creds)
        code = get_verification_code_from_gmail_api(service)
        if code:
            print(f"  [api] Got verification code: {code}")
            return code
    except Exception as e:
        print(f"  [api] Gmail code retrieval error: {e}")
    return ""


def _assign_device_profile(account):
    """
    Get the device profile for an account.

    Priority order:
      1. device_profile already on the account dict (passed in from caller)
      2. device_profile embedded inside the account's fingerprint
         (set during account creation — this is the canonical source)
      3. device_profile stored separately in Supabase (legacy)
      4. Assign a new random profile and save it (fallback for old accounts)
    """
    username = account.get("username", "")

    # 1. Already on the account dict
    if account.get("device_profile"):
        return account["device_profile"]

    # 2. Embedded in fingerprint (new unified flow)
    fp = account.get("fingerprint", {})
    if isinstance(fp, dict) and fp.get("device_profile"):
        return fp["device_profile"]

    # 3. Check Supabase
    from db.supabase_client import supabase
    try:
        resp = supabase.table("accounts") \
            .select("device_profile, fingerprint") \
            .eq("username", username) \
            .single() \
            .execute()

        if resp.data:
            if resp.data.get("device_profile"):
                return resp.data["device_profile"]
            stored_fp = resp.data.get("fingerprint")
            if isinstance(stored_fp, dict) and stored_fp.get("device_profile"):
                return stored_fp["device_profile"]
    except Exception:
        pass

    # 4. Fallback: assign new random profile (legacy accounts without one)
    profile = random.choice(DEVICE_PROFILES)
    try:
        supabase.table("accounts") \
            .update({"device_profile": profile}) \
            .eq("username", username) \
            .execute()
        print(f"  [api] Assigned new device: {profile['manufacturer']} {profile['model']}")
    except Exception as e:
        print(f"  [api] Could not save device profile: {e}")

    return profile


def _apply_device_profile(client, profile):
    """Apply a device profile to an instagrapi Client."""
    client.set_device({
        "manufacturer": profile["manufacturer"],
        "model": profile["model"],
        "android_version": profile["android_version"],
        "android_release": profile["android_release"],
        "dpi": profile["dpi"],
        "resolution": profile["resolution"],
        "cpu": profile["cpu"],
        "version_code": profile["version_code"],
    })


def create_api_client(account):
    """
    Create an authenticated instagrapi Client with:
    - Unique device fingerprint per account (stored in Supabase)
    - UUID preservation on re-login (prevents challenge loops)
    - Proxy setup via get_fresh_proxy()
    - Challenge resolution via Gmail

    Args:
        account: dict with username, password, email, proxy_url

    Returns:
        Client instance (logged in), or None on failure
    """
    username = account.get("username", "")
    password = account.get("password", "")
    email = account.get("email", "")
    session_file = _get_session_path(username)

    # Get the device profile that matches what was used during account creation
    device_profile = _assign_device_profile(account)

    cl = Client()
    cl.delay_range = [1, 3]

    # Apply unique device fingerprint
    _apply_device_profile(cl, device_profile)

    # Set proxy — prefer the account's existing proxy session (same IP as creation)
    # Only fall back to get_fresh_proxy() for daily use when no proxy_url is provided
    proxy_url = account.get("proxy_url") or get_fresh_proxy(username)
    if proxy_url:
        cl.set_proxy(proxy_url)
        print(f"  [api] Proxy: {proxy_url[:40]}...")

    # Challenge handler — auto-fetches code from Gmail
    def challenge_handler(username_arg, choice):
        print(f"  [api] Challenge! Fetching code from Gmail for {email}...")
        code = _get_verification_code(email)
        return code if code else ""

    cl.challenge_code_handler = challenge_handler

    # Try loading saved session (with UUID preservation)
    saved_uuids = None
    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            cl.login(username, password)
            # Validate session
            cl.get_timeline_feed()
            print(f"  [api] Session loaded for @{username}")
            return cl
        except Exception:
            print(f"  [api] Saved session invalid, fresh login...")
            # Preserve UUIDs before creating fresh client
            try:
                saved_uuids = cl.get_settings().get("uuids")
            except Exception:
                pass

            # Create fresh client with same device profile
            cl = Client()
            cl.delay_range = [1, 3]
            _apply_device_profile(cl, device_profile)
            if proxy_url:
                cl.set_proxy(proxy_url)
            cl.challenge_code_handler = challenge_handler

            # Restore UUIDs to prevent Instagram seeing a "new device"
            if saved_uuids:
                cl.set_uuids(saved_uuids)
                print(f"  [api] Preserved device UUIDs across re-login")

    # Fresh login
    try:
        cl.login(username, password)
        cl.dump_settings(session_file)
        print(f"  [api] Logged in as @{username}")
        return cl
    except ChallengeRequired:
        print(f"  [api] Challenge required for @{username}")
        print(f"  [api] Clear via: python -m profile.clear_challenges --account {username}")
        return None
    except TwoFactorRequired:
        print(f"  [api] 2FA required for @{username}")
        return None
    except Exception as e:
        print(f"  [api] Login failed for @{username}: {e}")
        return None


def save_api_session(client, username):
    """Save API session to disk for reuse."""
    try:
        session_file = _get_session_path(username)
        client.dump_settings(session_file)
        print(f"  [api] Session saved for @{username}")
    except Exception as e:
        print(f"  [api] Error saving session for @{username}: {e}")
