"""
Hybrid signup test:
1. Create account via instagrapi (no CAPTCHA)
2. Clear ufac_www_bloks challenge via Playwright browser
3. Login via instagrapi API (same device fingerprint)
"""

import sys
import io
import os
import random
import string
import time
import secrets
import base64

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from instagrapi import Client
from playwright.sync_api import sync_playwright
from core.proxy import get_fresh_proxy
from core.api_client import DEVICE_PROFILES, save_api_session, API_SESSIONS_DIR
from core.utils import parse_proxy_url
from core.stealth import STEALTH_SCRIPT
from creator.gmail_api import (
    authenticate_gmail_api,
    build_gmail_service,
    get_verification_code_from_gmail_api,
)
from core.storage import save_account, update_account
from config import FANVUE_LINK, SESSIONS_DIR
from profile.setup import BIO_TEMPLATES


# ======== CONFIG ========
email = "redditakk4+1000014@gmail.com"
password = "Pass" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8)) + "!"
username = "aiko_ren_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
full_name = "Aiko Ren"

print(f"Email: {email}")
print(f"Username: {username}")
print(f"Password: {password}")


# ======== PHASE 1: CREATE ACCOUNT VIA INSTAGRAPI ========
print(f"\n{'='*50}")
print("PHASE 1: CREATE ACCOUNT (instagrapi)")
print(f"{'='*50}")

cl = Client()
cl.delay_range = [2, 5]
device = random.choice(DEVICE_PROFILES)
cl.set_device({k: device[k] for k in device})
print(f"Device: {device['manufacturer']} {device['model']}")

proxy = get_fresh_proxy("create_" + username)
if proxy:
    cl.set_proxy(proxy)
    print(f"Proxy: {proxy[:40]}...")

cl.get_signup_config()
print("Sending verification code...")
cl.send_verify_email(email)

print("Waiting 20s for email...")
time.sleep(20)
creds = authenticate_gmail_api()
service = build_gmail_service(creds)
code = get_verification_code_from_gmail_api(service, max_retries=8, retry_delay=5)
print(f"Code: {code}")

if not code:
    print("No code found!")
    sys.exit(1)

signup_code = cl.check_confirmation_code(email, code).get("signup_code")
print(f"Signup code: {signup_code}")

sn_nonce = base64.b64encode(
    f"{email}|{int(time.time())}|{secrets.token_bytes(24).hex()}".encode()
).decode()

data = {
    "is_secondary_account_creation": "true",
    "jazoest": str(random.randint(22300, 22399)),
    "tos_version": "row",
    "suggestedUsername": "",
    "sn_result": "",
    "do_not_auto_login_if_credentials_match": "false",
    "phone_id": cl.phone_id,
    "enc_password": cl.password_encrypt(password),
    "username": username,
    "first_name": full_name,
    "adid": cl.adid,
    "guid": cl.uuid,
    "day": "15",
    "month": "6",
    "year": "2004",
    "device_id": cl.android_device_id,
    "_uuid": cl.uuid,
    "email": email,
    "force_sign_up_code": signup_code,
    "qs_stamp": "",
    "sn_nonce": sn_nonce,
    "waterfall_id": cl.waterfall_id,
    "one_tap_opt_in": "true",
}

result = cl.private_request("accounts/create/", data, domain="www.instagram.com")

if not result.get("account_created"):
    print(f"CREATE FAILED: {result}")
    sys.exit(1)

pk = result.get("created_user", {}).get("pk")
print(f"ACCOUNT CREATED! @{username} pk={pk}")

# Save to Supabase immediately
save_account(email, username, password, proxy_url=proxy)
update_account(username, device_profile=device)


# ======== PHASE 2: CLEAR CHALLENGE VIA PLAYWRIGHT ========
print(f"\n{'='*50}")
print("PHASE 2: CLEAR CHALLENGE (Playwright browser)")
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

browser_login_started_at = int(time.time())
print(f"Browser login started at unix ts: {browser_login_started_at}")
print("Logging in via browser...")
page.goto(
    "https://www.instagram.com/accounts/login/",
    wait_until="domcontentloaded",
    timeout=60000,
)
time.sleep(8)

# Fill login form
for sel in ['input[name="username"]', 'input[name="email"]']:
    try:
        el = page.locator(sel).first
        if el.is_visible(timeout=3000):
            el.fill(username)
            break
    except:
        continue

time.sleep(1)

for sel in ['input[name="password"]', 'input[name="pass"]']:
    try:
        el = page.locator(sel).first
        if el.is_visible(timeout=2000):
            el.fill(password)
            break
    except:
        continue

time.sleep(1)

for sel in [
    'button[type="submit"]',
    'div[role="button"][aria-label="Log in"]',
    'button:has-text("Log in")',
]:
    try:
        btn = page.locator(sel).first
        if btn.is_visible(timeout=1000):
            btn.click()
            break
    except:
        continue

print("Login submitted, waiting for redirect...")
try:
    page.wait_for_load_state("networkidle", timeout=30000)
except:
    pass
time.sleep(15)

# Check URL multiple times (redirects can be slow)
url = page.url
print(f"URL after login: {url[:100]}")

# Wait a bit more if still on login page (redirect may be pending)
if "/accounts/login" in url:
    print("Still on login page, waiting 10s more...")
    time.sleep(10)
    url = page.url
    print(f"URL now: {url[:100]}")

# Handle challenge / code entry page
needs_code = "/challenge" in url or "/auth_platform" in url or "codeentry" in url
if not needs_code:
    # Check page content for code entry indicators
    try:
        body = page.evaluate("document.body.innerText")
        if "confirmation code" in body.lower() or "security code" in body.lower() or "enter the code" in body.lower():
            needs_code = True
            print("Code entry detected from page content!")
    except:
        pass

if needs_code:
    print("CHALLENGE / CODE ENTRY DETECTED!")
    print(f"URL: {url[:80]}")

    # Try to get the verification code from Gmail and enter it
    time.sleep(10)
    print("Getting verification code from Gmail...")
    challenge_creds = authenticate_gmail_api()
    challenge_service = build_gmail_service(challenge_creds)
    challenge_code = get_verification_code_from_gmail_api(
        challenge_service, max_retries=10, retry_delay=5, after_timestamp=browser_login_started_at
    )

    if challenge_code:
        print(f"Got code: {challenge_code}")
        # Find the code input field and enter it
        code_entered = False
        for sel in [
            'input[name="security_code"]',
            'input[name="code"]',
            'input[aria-label*="code"]',
            'input[aria-label*="Code"]',
            'input[type="number"]',
            'input[type="tel"]',
            'input[placeholder*="code"]',
            'input[placeholder*="Code"]',
            'input:not([name="username"]):not([name="password"])',
        ]:
            try:
                inp = page.locator(sel).first
                if inp.is_visible(timeout=3000):
                    inp.fill(challenge_code)
                    print(f"  Entered code via {sel}")
                    code_entered = True
                    break
            except:
                continue

        if code_entered:
            time.sleep(1)
            # Click confirm/submit
            for sel in [
                'button:has-text("Confirm")',
                'button:has-text("Submit")',
                'button:has-text("Next")',
                'button[type="submit"]',
                'div[role="button"]:has-text("Confirm")',
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        print(f"  Clicked confirm")
                        break
                except:
                    continue

            time.sleep(10)
            print(f"  URL after code entry: {page.url[:80]}")
        else:
            print("  Could not find code input field")
            # Debug: show page content
            body = page.evaluate("document.body.innerText")
            safe = body[:400].encode("ascii", "replace").decode("ascii")
            print(f"  Page: {safe}")
    else:
        print("Could not get code from Gmail")

    # Wait for challenge to fully clear
    print("Waiting for challenge to clear...")
    for i in range(24):
        time.sleep(5)
        try:
            cur = page.url
            if "/challenge" not in cur and "/auth_platform" not in cur and "codeentry" not in cur:
                print("Challenge cleared!")
                break
        except:
            pass
        if (i + 1) % 6 == 0:
            remaining = (24 - i - 1) * 5
            print(f"  {remaining}s remaining...")
    time.sleep(3)

# Dismiss popups
for _ in range(3):
    try:
        btn = page.locator('button:has-text("Not Now")').first
        if btn.is_visible(timeout=2000):
            btn.click()
            time.sleep(2)
    except:
        break

url = page.url
print(f"Final URL: {url[:80]}")

browser_ok = "/accounts/login" not in url and "/challenge" not in url
if browser_ok:
    print("BROWSER LOGIN SUCCESS!")
    cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    context.storage_state(path=cookie_path)
    print(f"Cookies saved")
else:
    print(f"Browser login issue (url={url})")
    print("Continuing anyway...")

# Keep browser open a bit for Instagram to register the session
time.sleep(5)
browser.close()
pw.stop()


# ======== PHASE 3: API LOGIN WITH SAME DEVICE ========
print(f"\n{'='*50}")
print("PHASE 3: API LOGIN (instagrapi)")
print(f"{'='*50}")

cl2 = Client()
cl2.delay_range = [2, 5]
cl2.set_device({k: device[k] for k in device})
if proxy:
    cl2.set_proxy(proxy)


def challenge_handler(u, c):
    print("  Getting challenge code from Gmail...")
    api_challenge_ts = int(time.time()) - 30
    time.sleep(10)
    c2 = authenticate_gmail_api()
    s2 = build_gmail_service(c2)
    return get_verification_code_from_gmail_api(s2, max_retries=5, retry_delay=3, after_timestamp=api_challenge_ts) or ""


cl2.challenge_code_handler = challenge_handler

try:
    cl2.login(username, password)
    print("API LOGIN SUCCESS!")

    info = cl2.account_info()
    print(f"@{info.username} | followers={info.follower_count}")

    # Set bio
    bio = random.choice(BIO_TEMPLATES)
    cl2.account_edit(biography=bio, external_url=FANVUE_LINK)
    print(f"Bio: {bio[:40]}...")

    save_api_session(cl2, username)
    update_account(username, api_session_saved=True)

    print(f"\nFULL SUCCESS! @{username} created + challenge cleared + API works!")

except Exception as e:
    print(f"API login failed: {type(e).__name__}: {e}")
    print("Account was created but API login needs challenge clearing first.")
