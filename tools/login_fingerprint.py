"""
Login to Instagram using saved browser fingerprints.
This ensures consistent browser identification for each account.
"""

import os
import sys
import time
import random

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from core.storage import get_account_by_username, get_fingerprint_by_username, load_accounts
from core.utils import human_delay
from core.stealth import STEALTH_SCRIPT


def login_with_fingerprint(username, password, headless=False):
    """
    Login to Instagram using the saved fingerprint for consistent browser identification.

    Args:
        username (str): Instagram username
        password (str): Instagram password
        headless (bool): Whether to run browser in headless mode

    Returns:
        tuple: (page, browser, context) for further automation, or (None, None, None) on failure
    """
    account = get_account_by_username(username)
    if not account:
        print(f"❌ Account '{username}' not found in saved accounts")
        return None, None, None

    fingerprint = account.get("fingerprint")
    if not fingerprint:
        print(f"⚠️ No fingerprint found for '{username}', using defaults")
        fingerprint = {}

    print(f"\n{'='*60}")
    print(f"🔐 Logging in with fingerprint: {fingerprint.get('device_model', 'iPhone 13')}")
    print(f"{'='*60}\n")

    try:
        with sync_playwright() as p:
            iphone = p.devices['iPhone 13']
            browser = p.chromium.launch(headless=headless, args=['--incognito'])

            context_params = {
                **iphone,
                'locale': 'en-US',
                'timezone_id': fingerprint.get('timezone', 'America/Los_Angeles'),
            }

            if fingerprint.get('user_agent'):
                context_params['user_agent'] = fingerprint.get('user_agent')

            if fingerprint.get('accept_language'):
                context_params['extra_http_headers'] = {
                    'Accept-Language': fingerprint.get('accept_language', 'en-US,en;q=0.9'),
                }

            context = browser.new_context(**context_params)
            context.add_init_script(STEALTH_SCRIPT)

            page = context.new_page()

            print("🌐 Navigating to Instagram...")
            page.goto("https://www.instagram.com/accounts/login/")
            human_delay(2, 3)

            print(f"📝 Entering username: {username}")
            username_input = page.locator('input[name="username"]')
            username_input.fill(username)
            human_delay(1, 2)

            print("🔑 Entering password...")
            password_input = page.locator('input[name="password"]')
            password_input.fill(password)
            human_delay(1, 2)

            print("➡️ Clicking login...")
            login_button = page.locator('button[type="button"]:has-text("Log in")').first
            login_button.click()

            print("⏳ Waiting for login to complete...")
            human_delay(3, 5)

            try:
                page.wait_for_url("**/feed/**", timeout=10000)
                print(f"✅ Successfully logged in as {username}!")
                print(f"Found fingerprint: {fingerprint.get('device_model')}")
                print(f"Browser will stay open for further automation...")
                return page, browser, context
            except:
                print(f"⚠️ Login may require 2FA or additional verification")
                print(f"Browser is open - complete login manually if needed")
                time.sleep(30)
                return page, browser, context

    except Exception as e:
        print(f"❌ Error during login: {e}")
        return None, None, None


def list_accounts_with_fingerprints():
    """List all saved accounts with their fingerprints."""
    accounts = load_accounts()
    if not accounts:
        print("❌ No saved accounts found")
        return

    print(f"\n{'='*60}")
    print(f"📋 Saved Accounts with Fingerprints:")
    print(f"{'='*60}")

    for i, account in enumerate(accounts, 1):
        fingerprint = account.get("fingerprint", {})
        device = fingerprint.get("device_model", "Unknown")
        user_agent_snippet = fingerprint.get("user_agent", "N/A")[:50]

        print(f"\n{i}. Username: {account.get('username')}")
        print(f"   Email: {account.get('email')}")
        print(f"   Device: {device}")
        print(f"   User Agent: {user_agent_snippet}...")
        print(f"   Timezone: {fingerprint.get('timezone', 'America/Los_Angeles')}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    print("Instagram Login with Fingerprint Support")
    print("========================================\n")
    list_accounts_with_fingerprints()
