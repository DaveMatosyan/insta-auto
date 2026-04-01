"""
Instagram account creation logic.

Split into small helper functions for readability and debugging.
Each _step_* function handles one screen in the Instagram signup flow.
"""

import time
import os
import re
import random

from playwright.sync_api import sync_playwright

from config import (
    BASE_EMAIL_PREFIX, EMAIL_DOMAIN, STOP_SEC,
    USE_GMAIL_API, SESSIONS_DIR, BLOCK_IMAGES,
    IMAGES_DIR, PROJECT_ROOT,
)
from core.utils import generate_random_string, print_account_info, generate_browser_fingerprint, parse_proxy_url, human_delay
from core.storage import save_account
from core.stealth import STEALTH_SCRIPT

# Import Gmail method based on config
if USE_GMAIL_API:
    from creator.gmail_api import authenticate_gmail_api, build_gmail_service, get_verification_code_from_gmail_api
else:
    import imaplib


# Default post captions for random selection
DEFAULT_CAPTIONS = [
    "Check me out!",
    "Living my best life",
    "Feeling good!",
    "Just vibing",
    "Smile more",
    "Life is beautiful",
    "Blessed and grateful",
    "One hot day!",
    "Catch me if you can",
    "Love this moment",
    "Excited for what's ahead",
    "Making memories",
    "Golden hour magic",
    "Feeling myself",
    "Living for moments like these",
    "Good vibes only",
    "Just being me",
    "This is my life",
    "Taking it one day at a time",
    "Spreading positivity",
]

# --- TIMING CONSTANTS ---
NAV_TIMEOUT = 30000
ELEMENT_TIMEOUT = 15000
CLICK_TIMEOUT = 10000


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def get_random_image(image_dir=None, exclude_pattern=None):
    """
    Get a random image from the images directory.

    Args:
        image_dir (str): Path to the images directory (defaults to config IMAGES_DIR)
        exclude_pattern (str): Pattern to exclude

    Returns:
        str: Full path to random image, or None if no images found
    """
    try:
        if image_dir is None:
            image_dir = IMAGES_DIR

        if not os.path.exists(image_dir):
            print(f"Images directory not found: {image_dir}")
            return None

        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        image_files = [
            f for f in os.listdir(image_dir)
            if os.path.isfile(os.path.join(image_dir, f)) and
            os.path.splitext(f)[1].lower() in valid_extensions
        ]

        if exclude_pattern:
            image_files = [f for f in image_files if exclude_pattern.lower() not in f.lower()]

        if not image_files:
            print(f"No image files found in {image_dir}" + (f" (excluding {exclude_pattern})" if exclude_pattern else ""))
            return None

        selected_image = random.choice(image_files)
        full_path = os.path.join(image_dir, selected_image)
        print(f"Randomly selected image: {selected_image}")
        return full_path

    except Exception as e:
        print(f"Error getting random image: {e}")
        return None


# ---------------------------------------------------------------------------
# Verification code helpers
# ---------------------------------------------------------------------------

def get_verification_code_wrapper(email_to_check, max_retries=15, retry_delay=3):
    """Wrapper to retrieve verification code using API or IMAP."""
    if USE_GMAIL_API:
        try:
            print("Authenticating with Gmail API...")
            creds = authenticate_gmail_api()
            if not creds:
                print("Failed to authenticate with Gmail API")
                return None

            service = build_gmail_service(creds)
            return get_verification_code_from_gmail_api(service, max_retries, retry_delay)
        except Exception as e:
            print(f"Gmail API error: {e}")
            return None
    else:
        return get_verification_code_from_gmail_imap(email_to_check, max_retries, retry_delay)


def get_verification_code_from_gmail_imap(email_to_check, max_retries=12, retry_delay=5):
    """Retrieve Instagram verification code from Gmail inbox via IMAP."""
    try:
        print(f"\nFetching verification code from Gmail (IMAP) for {email_to_check}...")
        print(f"Checking mailbox (max {max_retries} attempts)...\n")

        for attempt in range(max_retries):
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                from config import GMAIL_EMAIL, GMAIL_PASSWORD
                mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
                mail.select("INBOX")

                status, messages = mail.search(None, 'FROM "Instagram" OR FROM "noreply@instagram.com"')

                if messages[0]:
                    email_ids = messages[0].split()[-10:]

                    for email_id in reversed(email_ids):
                        status, msg_data = mail.fetch(email_id, "(RFC822)")

                        if msg_data:
                            email_body = msg_data[0][1].decode('utf-8', errors='ignore').lower()
                            code_match = re.search(r'\b(\d{6})\b', email_body)

                            if code_match:
                                verification_code = code_match.group(1)
                                print(f"Found verification code: {verification_code}")
                                mail.close()
                                mail.logout()
                                return verification_code

                mail.close()
                mail.logout()

                if attempt < max_retries - 1:
                    print(f"Code not found yet. Attempt {attempt + 1}/{max_retries}")
                    print(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

            except Exception as e:
                print(f"Gmail connection error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        print(f"Could not retrieve verification code after {max_retries} attempts")
        return None

    except Exception as e:
        print(f"Error fetching verification code: {e}")
        return None


# ---------------------------------------------------------------------------
# Browser setup
# ---------------------------------------------------------------------------

def _setup_browser(playwright, fingerprint, proxy_url=None):
    """Launch browser and create a stealth context.

    Returns:
        tuple: (browser, context, page)
    """
    screen_width = random.choice([375, 390, 393, 412, 414, 430])
    screen_height = random.choice([812, 844, 851, 915, 896, 932])

    browser = playwright.chromium.launch(
        headless=False,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            '--disable-sync',
            '--disable-default-apps',
            '--disable-preconnect',
        ]
    )

    ctx_kwargs = dict(
        viewport={'width': screen_width, 'height': screen_height},
        user_agent=fingerprint.get('user_agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'),
        locale='en-US',
        timezone_id=fingerprint.get('timezone', 'America/Los_Angeles'),
        permissions=[],
        geolocation=None,
        is_mobile=True,
        has_touch=True,
        device_scale_factor=random.choice([2, 3]),
        extra_http_headers={
            'Accept-Language': fingerprint.get('accept_language', 'en-US,en;q=0.9'),
        }
    )
    if proxy_url:
        ctx_kwargs["proxy"] = parse_proxy_url(proxy_url)

    context = browser.new_context(**ctx_kwargs)

    if BLOCK_IMAGES:
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda route: route.abort())

    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()

    return browser, context, page


# ---------------------------------------------------------------------------
# Signup flow steps  (each handles one Instagram screen)
# ---------------------------------------------------------------------------

def _step_navigate_to_signup(page):
    """Navigate to signup pages (phone first, then email)."""
    print("Step 1: Navigating to phone signup page...")
    page.goto("https://www.instagram.com/accounts/signup/phone/", timeout=NAV_TIMEOUT)
    human_delay(2, 4)

    print("Step 2: Navigating to email signup page...")
    page.goto("https://www.instagram.com/accounts/signup/email/", timeout=NAV_TIMEOUT)
    human_delay(3, 5)

    # Switch to email view if needed
    try:
        switch_btn = page.locator('div[role="button"], button').filter(has_text="Sign up with email").first
        if switch_btn.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Switching to Email view...")
            switch_btn.click()
            human_delay(1, 2)
    except:
        pass


def _step_enter_email(page, email):
    """Enter email and click Next."""
    try:
        print("Entering Email...")
        page.locator('input[aria-label="Email"]').wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
        page.locator('input[aria-label="Email"]').fill(email)
        human_delay(1, 2)

        print("Clicking Next...")
        try:
            page.get_by_role("button", name="Next").first.click(timeout=CLICK_TIMEOUT)
        except:
            page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
        human_delay(2, 4)

    except Exception as e:
        print(f"Error in Email step: {e}")


def _step_verify_code(page, email):
    """Wait for code field, retrieve code from Gmail, and submit it.

    Returns:
        bool: True if code was submitted, False on failure.
    """
    print("\n" + "=" * 60)
    print(f" RETRIEVING VERIFICATION CODE FROM GMAIL (API MODE)")
    print(f" Email: {email}")
    print("=" * 60)

    try:
        page.locator('input[aria-label="Confirmation code"]').wait_for(state="visible", timeout=20000)
    except:
        print("Warning: Code field didn't appear automatically. Continuing...")

    print("Waiting 15s for Instagram to deliver the email...")
    time.sleep(15)
    verification_code = get_verification_code_wrapper(email, max_retries=30, retry_delay=10)

    if not verification_code:
        print("Failed to retrieve verification code!")
        print("Browser will stay open for inspection...")
        time.sleep(30)
        return False

    print(f"Entering code: {verification_code}")
    page.locator('input[aria-label="Confirmation code"]').fill(verification_code)
    human_delay(1, 2)

    print("Clicking Next...")
    try:
        page.get_by_role("button", name="Next").first.click(timeout=CLICK_TIMEOUT)
    except:
        page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
    human_delay(2, 4)

    return True


def _step_fill_profile(page, fullname, password):
    """Fill Full Name + Password on the profile details screen."""
    print("Waiting for Profile Details screen...")
    human_delay(4, 6)

    try:
        if page.locator('input[aria-label="Full Name"]').is_visible(timeout=ELEMENT_TIMEOUT):
            print("Filling Full Name...")
            page.locator('input[aria-label="Full Name"]').fill(fullname)
            human_delay(1, 2)

        if page.locator('input[aria-label="Password"]').is_visible(timeout=ELEMENT_TIMEOUT):
            print("Filling Password...")
            page.locator('input[aria-label="Password"]').fill(password)
            human_delay(1, 2)

        try:
            page.locator('input[type="checkbox"]').check()
        except:
            pass

        print("Clicking Next/Sign Up...")
        try:
            page.locator('div[role="button"]:has-text("Next")').last.click(timeout=CLICK_TIMEOUT)
        except:
            page.locator('div[role="button"]:has-text("Sign up")').last.click(force=True)
        human_delay(2, 4)

    except Exception as e:
        print(f"Error filling profile details: {e}")


def _step_birthday(page):
    """Set a random birthday and click Next."""
    print("Waiting for Birthday screen...")
    human_delay(4, 6)
    try:
        year = random.randint(1997, 2000)
        month = random.randint(1, 12)
        day = random.randint(1, 28)

        # Instagram uses a plain text input with MM/DD/YYYY format
        birthday_str = f"{month:02d}/{day:02d}/{year:04d}"
        print(f"Setting random birthday: {birthday_str}")

        # Try the text input first (current Instagram signup flow)
        birthday_input = page.locator('input[name="birthday"], input[aria-label*="Birthday"], input[aria-label*="birthday"]').first
        if not birthday_input.is_visible(timeout=3000):
            # Fallback: any text input on the page that's not already filled
            birthday_input = page.locator('input[type="text"]').first

        if birthday_input.is_visible(timeout=ELEMENT_TIMEOUT):
            birthday_input.click()
            human_delay(0.5, 1)
            # Clear existing value and type the birthday
            birthday_input.fill("")
            human_delay(0.3, 0.5)
            birthday_input.type(birthday_str, delay=80)
            human_delay(1, 2)
            print(f"Birthday set to: {birthday_str}")
        else:
            # Fallback: try input[type="date"] format
            print("Text input not found, trying date input...")
            date_input = page.locator('input[type="date"]').first
            if date_input.is_visible(timeout=3000):
                date_input.fill(f"{year:04d}-{month:02d}-{day:02d}")
                human_delay(1, 2)
            else:
                print("Could not find any birthday input field")

        human_delay(1, 2)
        print("Clicking Next...")
        page.locator('div[role="button"]:has-text("Next")').last.click()
        human_delay(2, 4)

    except Exception as e:
        print(f"Birthday step error: {e}")


def _step_fullname(page, fullname):
    """Fill the separate Full Name screen (appears after birthday)."""
    print("Waiting for Full Name screen...")
    human_delay(4, 6)
    try:
        fullname_input = page.locator('input[aria-label="Full name"]')
        if fullname_input.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Filling Full Name...")
            fullname_input.click()
            human_delay(1, 2)
            fullname_input.fill(fullname)
            human_delay(1, 2)

            print("Clicking Next...")
            page.locator('div[role="button"]:has-text("Next")').last.click()
            human_delay(2, 4)
    except Exception as e:
        print(f"Full Name step error: {e}")


def _step_username(page, username):
    """Fill the Username screen."""
    print("Waiting for Username screen...")
    human_delay(4, 6)
    try:
        username_input = page.locator('input[aria-label="Username"]')
        if username_input.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Filling Username...")
            username_input.fill(username)
            human_delay(2, 4)

            print("Clicking Next...")
            page.locator('div[role="button"]:has-text("Next")').last.click()
            human_delay(2, 4)
    except Exception as e:
        print(f"Username step error: {e}")


def _step_accept_terms(page):
    """Click 'I agree' on the Terms screen."""
    print("Waiting for Terms agreement screen...")
    human_delay(4, 6)
    try:
        agree_button = page.locator('div[role="button"][aria-label="I agree"]').first

        if agree_button.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Clicking 'I agree' button...")
            agree_button.click()
            human_delay(20, 25)
        else:
            page.locator('div[role="button"]:has-text("I agree")').first.click()
            human_delay(20, 25)

        print("Terms accepted!")

    except Exception as e:
        print(f"Terms agreement error: {e}")


# ---------------------------------------------------------------------------
# Post-signup helpers
# ---------------------------------------------------------------------------

def _browser_setup(page, context, username):
    """
    Set up profile directly in the browser after account creation.
    Sets bio, uploads profile pic, uploads 3 posts, saves cookies.
    Non-fatal — if this fails, the account is still saved.
    """
    try:
        from core.browser_profile import update_bio, upload_profile_pic, upload_post
        from profile.setup import BIO_TEMPLATES, POST_CAPTIONS, get_profile_images
        from config import FANVUE_LINK

        print("\n--- Browser Setup: Profile + Posts ---")

        # Unblock images for uploads
        if BLOCK_IMAGES:
            context.unroute("**/*.{png,jpg,jpeg,gif,webp,svg}")

        # Set bio + linktree
        bio = random.choice(BIO_TEMPLATES)
        if update_bio(page, bio, FANVUE_LINK):
            print(f"[setup] Bio set: {bio[:50]}...")
        else:
            print("[setup] Bio update failed")

        # Upload profile pic
        images = get_profile_images()
        if images:
            pfp_image = random.choice(images)
            if upload_profile_pic(page, pfp_image):
                print(f"[setup] Profile pic uploaded")
            else:
                print("[setup] Profile pic upload failed")
        else:
            print("[setup] No images in data/profile_images/ — skipping pfp")

        # Upload 3 posts
        if images:
            selected = random.sample(images, min(3, len(images)))
            for i, img in enumerate(selected):
                caption = random.choice(POST_CAPTIONS)
                if upload_post(page, img, caption):
                    print(f"[setup] Posted {i+1}/{len(selected)}: {os.path.basename(img)}")
                else:
                    print(f"[setup] Post {i+1} failed")
                    break
                time.sleep(random.uniform(15, 30))
        else:
            print("[setup] No images — skipping posts")

        # Save cookies after setup
        cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
        context.storage_state(path=cookie_path)
        print(f"[setup] Cookies saved after full setup")
        print("[setup] Browser setup complete!")

    except Exception as e:
        print(f"[setup] Error (non-fatal): {e}")


def _save_session_and_bump_config(context, username, email, password, fullname,
                                   fingerprint, proxy_url):
    """Save account to JSON, save cookies, bump START_NUMBER in config."""
    print("\n" + "=" * 60)
    print("ACCOUNT CREATION COMPLETE!")
    print("=" * 60)
    print(f"EMAIL: {email}")
    print(f"USERNAME: {username}")
    print(f"PASSWORD: {password}")
    print(f"FULL NAME: {fullname}")
    print("=" * 60)

    save_account(email, username, password, fingerprint, proxy_url=proxy_url)

    # Save session cookies
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
        context.storage_state(path=cookie_path)
        print(f"Saved session cookies to {cookie_path}")
    except Exception as e:
        print(f"Could not save cookies: {e}")

    # Browser setup — set bio + upload pfp + 3 posts (done later in create_account)

    # Bump START_NUMBER in config.py
    try:
        config_path = os.path.join(PROJECT_ROOT, 'config.py')
        with open(config_path, 'r', encoding='utf-8') as f:
            config_content = f.read()

        match = re.search(r'START_NUMBER = (\d+)', config_content)
        if match:
            current_num = int(match.group(1))
            new_num = current_num + 1
            updated_content = re.sub(r'START_NUMBER = \d+', f'START_NUMBER = {new_num}', config_content)

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print(f"Updated START_NUMBER from {current_num} to {new_num}")
    except Exception as e:
        print(f"Could not update START_NUMBER: {e}")


def _handle_onboarding_modals(page):
    """Dismiss 'Not Now', 'Not now', 'Save info', 'Close', and 'Skip' modals after signup."""
    print("\nHandling onboarding modals...")
    human_delay(2, 3)

    # Dismiss "Save your login info?" modal — click "Not now" (lowercase)
    for dismiss_text in ["Not now", "Not Now"]:
        try:
            btn = page.locator(f'button:has-text("{dismiss_text}"), div[role="button"]:has-text("{dismiss_text}")').first
            if btn.is_visible(timeout=5000):
                print(f"Clicking '{dismiss_text}' button...")
                btn.click()
                human_delay(2, 3)
                break
        except Exception:
            continue

    # Close X button on any modal
    try:
        close_btn = page.locator('div[role="button"][aria-label="Close"], button[aria-label="Close"], svg[aria-label="Close"]').first
        if close_btn.is_visible(timeout=5000):
            print("Closing modal...")
            close_btn.click()
            human_delay(1, 2)
    except Exception:
        pass

    # Skip onboarding steps
    for skip_i in range(3):
        try:
            skip_btn = page.locator('div[role="button"]:has-text("Skip"), button:has-text("Skip")').first
            if skip_btn.is_visible(timeout=5000):
                print(f"Skipping step {skip_i + 1}/3...")
                skip_btn.click()
                human_delay(2, 3)
            else:
                break
        except Exception:
            break

    # Dismiss "Turn on Notifications" popup
    for dismiss_text in ["Not Now", "Not now"]:
        try:
            btn = page.locator(f'button:has-text("{dismiss_text}")').first
            if btn.is_visible(timeout=3000):
                print(f"Dismissing notifications popup...")
                btn.click()
                human_delay(1, 2)
                break
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def create_account(email_number, proxy_url=None):
    """Create a single Instagram account.

    Orchestrates the full signup flow:
      1. Launch stealth browser
      2. Navigate to signup
      3. Enter email
      4. Retrieve & submit verification code
      5. Fill profile (name + password)
      6. Set birthday
      7. Fill full name (separate screen)
      8. Fill username
      9. Accept terms
     10. Save account + session
     11. Handle onboarding modals
     12. Browser setup (bio + pfp + 3 posts + save cookies)

    Args:
        email_number (int): Email suffix number
        proxy_url (str): Proxy URL to route traffic through (optional)
    """
    email = f"{BASE_EMAIL_PREFIX}+{email_number}{EMAIL_DOMAIN}"
    fingerprint = generate_browser_fingerprint()

    print(f"Generated Browser Fingerprint: {fingerprint['device_model']}")
    print(f"Timezone: {fingerprint.get('timezone', 'America/Los_Angeles')}")
    print(f"User Agent: {fingerprint.get('user_agent', 'None')}")
    if proxy_url:
        print(f"Proxy: {proxy_url[:50]}...")

    password = "Pass" + generate_random_string(8) + "!"
    fullname = "Aiko Ren"
    username = "aiko_ren_" + generate_random_string(5)

    print(f"\n{'='*60}")
    print(f"Creating account #{email_number}")
    if proxy_url:
        print(f"Proxy: {proxy_url[:50]}")
    print(f"Email: {email}")
    print(f"Password: {password}")
    print(f"Full Name: {fullname}")
    print(f"Username: {username}")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        browser, context, page = _setup_browser(p, fingerprint, proxy_url)

        try:
            _step_navigate_to_signup(page)
            _step_enter_email(page, email)

            if not _step_verify_code(page, email):
                return False

            _step_fill_profile(page, fullname, password)
            _step_birthday(page)
            _step_fullname(page, fullname)
            _step_username(page, username)
            _step_accept_terms(page)

            _save_session_and_bump_config(
                context, username, email, password, fullname,
                fingerprint, proxy_url,
            )

            _handle_onboarding_modals(page)

            # Full profile setup: bio + pfp + 3 posts + save cookies
            _browser_setup(page, context, username)

            print("\nAll tasks completed! Closing browser...")
            human_delay(2, 3)

            return True

        except Exception as e:
            print(f"\nERROR creating account: {e}")
            print("Browser will stay open for 30 seconds for inspection...")
            time.sleep(30)
            return False

        finally:
            browser.close()
