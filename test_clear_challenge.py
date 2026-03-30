"""
Test: Clear ufac_www_bloks challenge on existing account.
Phase 2: Playwright browser login + auto code entry
Phase 3: instagrapi API login to verify challenge is cleared
"""

import sys
import io
import os
import time
import random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
from instagrapi import Client
from core.proxy import get_fresh_proxy
from core.api_client import DEVICE_PROFILES, save_api_session
from core.utils import parse_proxy_url
from core.stealth import STEALTH_SCRIPT
from creator.gmail_api import (
    authenticate_gmail_api,
    build_gmail_service,
    get_verification_code_from_gmail_api,
)
from core.storage import update_account
from config import SESSIONS_DIR, FANVUE_LINK
from profile.setup import BIO_TEMPLATES
from db.supabase_client import supabase

# Pick an account that exists but doesn't have API working
TARGET_USERNAME = "aiko_ren_xq44o"

# Get account details
resp = supabase.table("accounts").select("*").eq("username", TARGET_USERNAME).single().execute()
account = resp.data
username = account["username"]
password = account["password"]
email = account["email"]

print(f"Account: @{username}")
print(f"Email: {email}")
print(f"Password: {password[:6]}...")

# Get proxy
proxy = get_fresh_proxy(username)
print(f"Proxy: {proxy[:40]}..." if proxy else "No proxy")


# ======== PHASE 2: CLEAR CHALLENGE VIA PLAYWRIGHT ========
print(f"\n{'='*50}")
print("PHASE 2: CLEAR CHALLENGE (Playwright)")
print(f"{'='*50}")

pw = sync_playwright().start()
browser = pw.chromium.launch(
    headless=False,
    args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"],
)

ctx_kwargs = {
    "viewport": {"width": 390, "height": 844},
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
    "locale": "en-US",
    "timezone_id": "America/Los_Angeles",
    "is_mobile": True,
    "has_touch": True,
}
if proxy:
    ctx_kwargs["proxy"] = parse_proxy_url(proxy)

context = browser.new_context(**ctx_kwargs)
context.add_init_script(STEALTH_SCRIPT)
page = context.new_page()

login_started_at = int(time.time())  # record time before login triggers any code email
print(f"Login started at unix ts: {login_started_at}")
print("Navigating to login...")
page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=90000)
print("Page loaded, waiting for form...")
time.sleep(10)

# Fill login
print("Filling login form...")
for sel in ['input[name="username"]', 'input[name="email"]']:
    try:
        el = page.locator(sel).first
        if el.is_visible(timeout=5000):
            el.fill(username)
            print(f"  Username filled via {sel}")
            break
    except:
        continue

time.sleep(1)

for sel in ['input[name="password"]', 'input[name="pass"]']:
    try:
        el = page.locator(sel).first
        if el.is_visible(timeout=3000):
            el.fill(password)
            print(f"  Password filled via {sel}")
            break
    except:
        continue

time.sleep(1)

# Click login
print("Clicking login...")
for sel in [
    'button[type="submit"]',
    'div[role="button"][aria-label="Log in"]',
    'button:has-text("Log in")',
    'div[role="button"]:has-text("Log in")',
]:
    try:
        btn = page.locator(sel).first
        if btn.is_visible(timeout=2000):
            btn.click()
            print(f"  Clicked via {sel}")
            break
    except:
        continue

print("Login submitted, waiting for redirect (up to 60s)...")

# Wait up to 60s for the URL to change from /accounts/login/
url = ""
for i in range(12):  # 12 * 5 = 60s
    time.sleep(5)
    try:
        url = page.url
        if "/accounts/login" not in url:
            print(f"Redirected to: {url[:100]}")
            break
    except:
        pass
    if (i + 1) % 3 == 0:
        print(f"  Still waiting... ({(i+1)*5}s)")

# Wait for the new page to fully load
try:
    page.wait_for_load_state("networkidle", timeout=15000)
except:
    pass
time.sleep(5)

url = page.url
print(f"Current URL: {url[:100]}")

# Read page content
body = ""
try:
    body = page.evaluate("document.body.innerText")
    safe_body = body[:300].encode("ascii", "replace").decode("ascii")
    print(f"Page: {safe_body[:200]}")
except:
    print("Could not read page content")
    time.sleep(5)
    try:
        body = page.evaluate("document.body.innerText") or ""
    except:
        pass

# Detect if we need to enter a code
needs_code = (
    "/challenge" in url
    or "/auth_platform" in url
    or "codeentry" in url
    or "confirmation code" in body.lower()
    or "security code" in body.lower()
    or "enter the code" in body.lower()
    or "enter the 6-digit" in body.lower()
    or "we sent a code" in body.lower()
)

if needs_code:
    print(f"\n>>> CODE ENTRY NEEDED! <<<")
    print("Getting verification code from Gmail...")
    time.sleep(10)

    creds = authenticate_gmail_api()
    service = build_gmail_service(creds)
    code = get_verification_code_from_gmail_api(service, max_retries=12, retry_delay=5, after_timestamp=login_started_at)

    if code:
        print(f"Got code: {code}")

        # Try to find and fill the code input
        code_entered = False
        for sel in [
            'input[name="security_code"]',
            'input[name="code"]',
            'input[name="verificationCode"]',
            'input[aria-label*="code" i]',
            'input[aria-label*="Code"]',
            'input[type="number"]',
            'input[type="tel"]',
            'input[placeholder*="code" i]',
            'input[placeholder*="Code"]',
            'input[autocomplete="one-time-code"]',
            # Generic: any visible input that's not username/password
            'input:not([name="username"]):not([name="password"]):not([name="email"]):not([name="pass"]):not([type="hidden"])',
        ]:
            try:
                inp = page.locator(sel).first
                if inp.is_visible(timeout=2000):
                    inp.click()
                    time.sleep(0.5)
                    inp.fill(code)
                    print(f"  Code entered via: {sel}")
                    code_entered = True
                    break
            except:
                continue

        if not code_entered:
            # Debug: list all visible inputs
            inputs = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(el => ({
                    name: el.name, type: el.type, placeholder: el.placeholder,
                    ariaLabel: el.getAttribute('aria-label') || '',
                    visible: el.offsetParent !== null
                })).filter(i => i.visible);
            }""")
            print(f"  Visible inputs: {inputs}")

        if code_entered:
            time.sleep(1)
            # Debug: list all visible buttons so we know exact text
            try:
                btns_debug = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('button, div[role="button"]')).map(el => ({
                        text: el.innerText.trim().slice(0, 60),
                        type: el.getAttribute('type') || '',
                        visible: el.offsetParent !== null
                    })).filter(b => b.visible && b.text);
                }""")
                print(f"  Visible buttons: {btns_debug}")
            except:
                pass

            # Click confirm/submit
            btn_clicked = False
            for sel in [
                'button:has-text("Confirm")',
                'button:has-text("Submit")',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button:has-text("OK")',
                'button:has-text("Verify")',
                'button[type="submit"]',
                'div[role="button"]:has-text("Confirm")',
                'div[role="button"]:has-text("Next")',
                'div[role="button"]:has-text("Submit")',
                'div[role="button"]:has-text("Continue")',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        print(f"  Submitted via: {sel}")
                        btn_clicked = True
                        break
                except:
                    continue

            if not btn_clicked:
                # Fallback: press Enter on the input
                print("  No button found — pressing Enter on input field")
                try:
                    page.keyboard.press("Enter")
                except:
                    pass

            print("Waiting for challenge to process...")
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except:
                pass
            time.sleep(10)
            print(f"URL after code: {page.url[:100]}")
    else:
        print("Could not get code from Gmail!")
        print("Browser stays open 60s for manual entry...")
        time.sleep(60)
else:
    print("No code entry needed")

# Dismiss popups
for _ in range(5):
    try:
        btn = page.locator('button:has-text("Not Now")').first
        if btn.is_visible(timeout=3000):
            btn.click()
            time.sleep(2)
    except:
        break

final_url = page.url
print(f"\nFinal URL: {final_url[:100]}")

is_logged_in = (
    "/accounts/login" not in final_url
    and "/challenge" not in final_url
    and "/auth_platform" not in final_url
)

if is_logged_in:
    print("BROWSER LOGIN SUCCESS!")
    cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    context.storage_state(path=cookie_path)
    print("Cookies saved")
else:
    print(f"Browser login not fully cleared yet")
    print("Waiting 30s for slow redirect...")
    time.sleep(30)

    # Re-check — the redirect to codeentry often happens late
    final_url = page.url
    print(f"URL after wait: {final_url[:100]}")

    # Check if we landed on code entry page NOW
    if "/auth_platform" in final_url or "codeentry" in final_url:
        print("\n>>> LATE CODE ENTRY DETECTED! <<<")
        # Try to read page and enter code
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(5)

        print("Getting code from Gmail...")
        time.sleep(5)
        creds2 = authenticate_gmail_api()
        service2 = build_gmail_service(creds2)
        code2 = get_verification_code_from_gmail_api(service2, max_retries=12, retry_delay=5, after_timestamp=login_started_at)

        if code2:
            print(f"Got code: {code2}")
            # Enter code
            for sel in [
                'input[name="security_code"]',
                'input[name="code"]',
                'input[name="verificationCode"]',
                'input[aria-label*="code" i]',
                'input[type="number"]',
                'input[type="tel"]',
                'input[autocomplete="one-time-code"]',
                'input:not([name="username"]):not([name="password"]):not([name="email"]):not([name="pass"]):not([type="hidden"])',
            ]:
                try:
                    inp = page.locator(sel).first
                    if inp.is_visible(timeout=3000):
                        inp.click()
                        time.sleep(0.5)
                        inp.fill(code2)
                        print(f"  Code entered via: {sel}")

                        # Submit
                        time.sleep(1)
                        late_btn_clicked = False
                        for btn_sel in [
                            'button:has-text("Confirm")',
                            'button:has-text("Submit")',
                            'button:has-text("Next")',
                            'button:has-text("Continue")',
                            'button:has-text("OK")',
                            'button:has-text("Verify")',
                            'button[type="submit"]',
                            'div[role="button"]:has-text("Confirm")',
                            'div[role="button"]:has-text("Next")',
                        ]:
                            try:
                                btn = page.locator(btn_sel).first
                                if btn.is_visible(timeout=2000):
                                    btn.click()
                                    print(f"  Submitted via: {btn_sel}")
                                    late_btn_clicked = True
                                    break
                            except:
                                continue
                        if not late_btn_clicked:
                            print("  No button found — pressing Enter")
                            try:
                                page.keyboard.press("Enter")
                            except:
                                pass

                        print("Waiting for verification...")
                        try:
                            page.wait_for_load_state("networkidle", timeout=30000)
                        except:
                            pass
                        time.sleep(15)
                        final_url = page.url
                        print(f"URL after code: {final_url[:100]}")
                        break
                except:
                    continue
        else:
            print("Could not get code! Browser open 60s for manual...")
            time.sleep(60)
            final_url = page.url

    # Dismiss popups again
    for _ in range(3):
        try:
            btn = page.locator('button:has-text("Not Now")').first
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(2)
        except:
            break

    final_url = page.url
    is_logged_in = (
        "/accounts/login" not in final_url
        and "/challenge" not in final_url
        and "/auth_platform" not in final_url
    )

    if is_logged_in:
        print("CHALLENGE CLEARED after code entry!")
        cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        context.storage_state(path=cookie_path)
        print("Cookies saved")
    else:
        print(f"Still not cleared. Final URL: {final_url[:100]}")

time.sleep(5)
browser.close()
pw.stop()


# ======== PHASE 3: API LOGIN TEST ========
print(f"\n{'='*50}")
print("PHASE 3: API LOGIN TEST (instagrapi)")
print(f"{'='*50}")

if not is_logged_in:
    print("Skipping — browser challenge not cleared")
    sys.exit(1)

# Get device profile
device_profile = account.get("device_profile")
if not device_profile:
    device_profile = random.choice(DEVICE_PROFILES)

cl = Client()
cl.delay_range = [2, 5]
cl.set_device({k: device_profile[k] for k in device_profile})
if proxy:
    cl.set_proxy(proxy)


def challenge_handler(u, c):
    print("  API challenge! Getting code from Gmail...")
    api_challenge_ts = int(time.time()) - 30  # look back 30s in case code arrived just before handler fired
    time.sleep(10)
    c2 = authenticate_gmail_api()
    s2 = build_gmail_service(c2)
    return get_verification_code_from_gmail_api(s2, max_retries=5, retry_delay=3, after_timestamp=api_challenge_ts) or ""


cl.challenge_code_handler = challenge_handler

try:
    cl.login(username, password)
    print("API LOGIN SUCCESS!")

    info = cl.account_info()
    print(f"@{info.username} | followers={info.follower_count} | posts={info.media_count}")

    # Set bio
    bio = random.choice(BIO_TEMPLATES)
    cl.account_edit(biography=bio, external_url=FANVUE_LINK)
    print(f"Bio: {bio[:40]}...")
    print(f"Link: {FANVUE_LINK}")

    save_api_session(cl, username)
    update_account(username, api_session_saved=True)

    print(f"\nFULL SUCCESS! Challenge cleared + API works for @{username}!")

except Exception as e:
    print(f"API login failed: {type(e).__name__}: {e}")
    # Print full last_json to understand the challenge type
    try:
        import json
        lj = cl.last_json
        print(f"last_json: {json.dumps(lj, indent=2)[:2000]}")
    except:
        pass
    print("Challenge may not have been fully cleared")
