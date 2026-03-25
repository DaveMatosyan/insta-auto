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
    """Dismiss 'Not Now', 'Close', and 'Skip' modals after signup."""
    print("\nHandling onboarding modals...")
    human_delay(2, 3)

    try:
        not_now_btn = page.locator('div[role="button"]:has-text("Not Now")').first
        if not_now_btn.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Clicking 'Not Now' button...")
            not_now_btn.click()
            human_delay(2, 3)
    except:
        pass

    try:
        close_btn = page.locator('div[role="button"][aria-label="Close"]').first
        if close_btn.is_visible(timeout=ELEMENT_TIMEOUT):
            print("Closing modal...")
            close_btn.click()
            human_delay(1, 2)
    except:
        pass

    for skip_i in range(3):
        try:
            skip_btn = page.locator('div[role="button"]:has-text("Skip")').first
            if skip_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                print(f"Skipping step {skip_i + 1}/3...")
                skip_btn.click()
                human_delay(2, 3)
            else:
                break
        except Exception:
            break


def _debug_page(page, label=""):
    """Print current page state for debugging."""
    try:
        url = page.url
        title = page.title()
        print(f"\n   [DEBUG {label}] URL: {url}")
        print(f"   [DEBUG {label}] Title: {title}")

        # List all visible buttons/links
        buttons = page.evaluate("""
            (() => {
                const els = [];
                document.querySelectorAll('button, a, div[role="button"], [role="menuitem"]').forEach(el => {
                    if (el.offsetParent !== null || el.offsetWidth > 0) {
                        const text = el.textContent?.trim().substring(0, 60) || '';
                        const aria = el.getAttribute('aria-label') || '';
                        const tag = el.tagName;
                        if (text || aria) els.push(`${tag}[${aria}] "${text}"`);
                    }
                });
                return els.slice(0, 25);
            })()
        """)
        if buttons:
            print(f"   [DEBUG {label}] Visible interactive elements ({len(buttons)}):")
            for b in buttons:
                print(f"      - {b}")

        # Count file inputs
        file_count = page.locator('input[type="file"]').count()
        print(f"   [DEBUG {label}] File inputs on page: {file_count}")
    except Exception as e:
        print(f"   [DEBUG {label}] Error reading page state: {e}")


def _upload_profile_picture(page, context):
    """Upload a random image as the profile picture.

    Flow on Instagram mobile web:
      1. Navigate to profile (already done by caller)
      2. Click "Edit profile" button
      3. On edit page, click the avatar / "Change profile photo"
      4. A bottom-sheet or dialog appears with "Upload Photo"
      5. Use the file input that becomes available
      6. Confirm / save

    Returns:
        str or None: Path to the image used (so we can exclude it from the post).
    """
    if BLOCK_IMAGES:
        context.unroute("**/*.{png,jpg,jpeg,gif,webp,svg}")

    print("\n" + "=" * 60)
    print("UPLOADING PROFILE PICTURE")
    print("=" * 60)
    human_delay(2, 3)

    profile_pic = get_random_image()
    if not profile_pic:
        print("No profile picture image found in images folder — skipping")
        return None

    print(f"Selected image: {os.path.basename(profile_pic)}")
    _debug_page(page, "PROFILE")

    # --- Step 1: Click "Edit profile" ---
    edit_clicked = False
    for selector in [
        'a:has-text("Edit profile")',
        'button:has-text("Edit profile")',
        'div[role="button"]:has-text("Edit profile")',
        'a[href*="/edit/"]',
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=5000):
                print("   Clicking 'Edit profile'...")
                el.click()
                human_delay(3, 5)
                edit_clicked = True
                break
        except Exception:
            continue

    if not edit_clicked:
        # Fallback: navigate directly to edit page
        print("   'Edit profile' button not found — navigating directly to edit URL")
        try:
            page.goto("https://www.instagram.com/accounts/edit/", timeout=NAV_TIMEOUT)
            human_delay(3, 5)
            edit_clicked = True
        except Exception as e:
            print(f"   Could not navigate to edit page: {e}")

    if not edit_clicked:
        print("   SKIP: Could not reach profile edit page")
        return profile_pic

    _debug_page(page, "EDIT PAGE")

    # --- Step 2: Click "Change profile photo" / avatar area ---
    change_clicked = False

    # Try clicking text links/buttons
    for text in ["Change profile photo", "Change photo", "Edit picture or avatar"]:
        try:
            el = page.locator(f'text="{text}"').first
            if el.is_visible(timeout=3000):
                print(f"   Clicking '{text}'...")
                el.click()
                human_delay(2, 4)
                change_clicked = True
                break
        except Exception:
            continue

    if not change_clicked:
        # Try clicking the avatar image itself (usually first img or inside a button)
        try:
            avatar = page.locator('img[data-testid="user-avatar"], header img, form img, button img').first
            if avatar.is_visible(timeout=3000):
                print("   Clicking avatar image...")
                avatar.click()
                human_delay(2, 4)
                change_clicked = True
        except Exception:
            pass

    if not change_clicked:
        # Try any button/link that looks like it relates to photo
        try:
            photo_btn = page.evaluate("""
                (() => {
                    const els = document.querySelectorAll('button, a, div[role="button"], span');
                    for (const el of els) {
                        const t = (el.textContent || '').toLowerCase();
                        if ((t.includes('photo') || t.includes('avatar') || t.includes('picture'))
                            && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            if photo_btn:
                print("   Clicked a photo-related element via JS scan")
                human_delay(2, 4)
                change_clicked = True
        except Exception:
            pass

    _debug_page(page, "AFTER CHANGE CLICK")

    # --- Step 3: Upload via file input ---
    uploaded = False

    # Wait a moment for any dialog/bottom-sheet to appear
    human_delay(1, 2)

    file_inputs = page.locator('input[type="file"]')
    file_count = file_inputs.count()
    print(f"   File inputs available: {file_count}")

    if file_count > 0:
        for idx in range(file_count):
            try:
                accept_attr = file_inputs.nth(idx).get_attribute("accept") or ""
                print(f"   Trying file input #{idx} (accept='{accept_attr}')...")
                file_inputs.nth(idx).set_input_files(profile_pic)
                human_delay(4, 6)

                _debug_page(page, f"AFTER UPLOAD #{idx}")

                # Look for Save/Done/Apply/Next button
                for btn_text in ['Save', 'Done', 'Apply', 'Next', 'Submit']:
                    try:
                        save_btn = page.locator(f'button:has-text("{btn_text}"), div[role="button"]:has-text("{btn_text}")').first
                        if save_btn.is_visible(timeout=5000):
                            print(f"   Clicking '{btn_text}'...")
                            save_btn.click()
                            human_delay(5, 8)
                            print("   Profile picture uploaded successfully!")
                            uploaded = True
                            break
                    except Exception:
                        continue

                if uploaded:
                    break
            except Exception as e:
                print(f"   File input #{idx} failed: {e}")
                continue
    else:
        # Maybe there's an "Upload Photo" menu item to click first
        print("   No file inputs yet — looking for 'Upload Photo' menu item...")
        try:
            upload_item = page.locator('text="Upload Photo"').first
            if upload_item.is_visible(timeout=5000):
                print("   Clicking 'Upload Photo'...")
                upload_item.click()
                human_delay(2, 3)

                # Now try file input again
                file_inputs = page.locator('input[type="file"]')
                file_count = file_inputs.count()
                print(f"   File inputs after menu click: {file_count}")
                if file_count > 0:
                    file_inputs.first.set_input_files(profile_pic)
                    human_delay(4, 6)
                    uploaded = True
                    print("   Profile picture uploaded!")
        except Exception as e:
            print(f"   Upload Photo menu not found: {e}")

    if not uploaded:
        print("   WARNING: Could not upload profile picture — continuing anyway")
        _debug_page(page, "PFP FAILED")

    return profile_pic


def _click_button_by_text(page, text, timeout=10000):
    """Try multiple selector strategies to click a button with given text.

    Returns True if clicked, False otherwise.
    """
    # Strategy 1: Playwright role selector
    try:
        btn = page.get_by_role("button", name=text).first
        if btn.is_visible(timeout=3000):
            btn.click()
            return True
    except Exception:
        pass

    # Strategy 2: div[role=button] with text
    try:
        btn = page.locator(f'div[role="button"]:has-text("{text}")').first
        if btn.is_visible(timeout=3000):
            btn.click()
            return True
    except Exception:
        pass

    # Strategy 3: button element with text
    try:
        btn = page.locator(f'button:has-text("{text}")').first
        if btn.is_visible(timeout=3000):
            btn.click()
            return True
    except Exception:
        pass

    # Strategy 4: JS scan all clickable elements
    try:
        clicked = page.evaluate(f"""
            (() => {{
                const els = document.querySelectorAll('button, div[role="button"], a, [role="menuitem"]');
                for (const el of els) {{
                    if (el.textContent?.trim() === '{text}' && el.offsetParent !== null) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
        """)
        if clicked:
            return True
    except Exception:
        pass

    return False


def _create_first_post(page, exclude_file=None):
    """Create the first post with a random image and caption.

    On mobile web Instagram doesn't have a "Create Post" button in the nav —
    the home page file inputs create Stories, not Posts.

    For NEW accounts, the profile page shows a "Share your first photo"
    onboarding button. We use that. If unavailable, we fall back to the
    hidden file inputs on the profile page (one of them triggers post creation).

    Flow:
      1. (Caller should have navigated to profile page already)
      2. Click "Share your first photo" or trigger the post file input
      3. Image appears → crop screen → Next
      4. Filter screen → Next
      5. Caption screen → write caption → Share
    """
    print("\n" + "=" * 60)
    print("CREATING FIRST POST")
    print("=" * 60)
    human_delay(2, 3)

    post_image = get_random_image(exclude_pattern=exclude_file)
    if not post_image:
        print("No post image found in images folder — skipping")
        return

    print(f"Selected image: {os.path.basename(post_image)}")
    _debug_page(page, "PROFILE PRE-POST")

    # --- Step 1: Trigger post creation from profile page ---
    create_triggered = False

    # Try "Share your first photo" onboarding button (new accounts)
    for text in ["Share your first photo", "Share your first post"]:
        try:
            btn = page.locator(f'div[role="button"]:has-text("{text}")').first
            if btn.is_visible(timeout=5000):
                print(f"   Clicking '{text}'...")
                btn.click()
                human_delay(3, 5)
                create_triggered = True
                break
        except Exception:
            continue

    if not create_triggered:
        # Try "Add profile photo" or any post-related prompt
        try:
            btn = page.locator('div[role="button"]:has-text("Add")').first
            if btn.is_visible(timeout=3000):
                btn_text = btn.inner_text()
                if 'photo' in btn_text.lower() or 'post' in btn_text.lower():
                    print(f"   Clicking '{btn_text.strip()[:40]}'...")
                    btn.click()
                    human_delay(3, 5)
                    create_triggered = True
        except Exception:
            pass

    _debug_page(page, "AFTER CREATE TRIGGER")

    # --- Step 2: Upload image ---
    # Check if we now have a post creation dialog or if we need to use file inputs
    uploaded = False

    # If a "Select from computer/gallery" button appeared, click it first
    for sel_text in ["Select from computer", "Select from gallery", "Select"]:
        try:
            sel_btn = page.locator(f'button:has-text("{sel_text}")').first
            if sel_btn.is_visible(timeout=3000):
                print(f"   Clicking '{sel_text}'...")
                sel_btn.click()
                human_delay(2, 3)
                break
        except Exception:
            continue

    # Now find and use file inputs
    file_inputs = page.locator('input[type="file"]')
    file_count = file_inputs.count()
    print(f"   File inputs available: {file_count}")

    if file_count > 0:
        # List all inputs and their accept attributes
        for idx in range(file_count):
            try:
                accept = file_inputs.nth(idx).get_attribute("accept") or ""
                print(f"      Input #{idx} accept='{accept}'")
            except Exception:
                pass

        # Try each file input — skip any that lead to story creation
        for idx in range(file_count):
            try:
                print(f"   Uploading to file input #{idx}...")
                file_inputs.nth(idx).set_input_files(post_image)
                human_delay(4, 6)

                # Check if we landed in story mode or post mode
                current_url = page.url
                if 'story' in current_url.lower():
                    print(f"   Input #{idx} opened story mode — wrong input, closing...")
                    # Close the story dialog
                    try:
                        close_btn = page.locator('button:has-text("Close")').first
                        if close_btn.is_visible(timeout=3000):
                            close_btn.click()
                            human_delay(1, 2)
                        # Handle "Discard" confirmation
                        discard_btn = page.locator('button:has-text("Discard")').first
                        if discard_btn.is_visible(timeout=3000):
                            discard_btn.click()
                            human_delay(1, 2)
                    except Exception:
                        pass
                    continue

                # Check if we got a crop/edit screen (= post creation)
                _debug_page(page, f"AFTER INPUT #{idx}")

                # Look for Next button (indicates post creation flow)
                has_next = False
                try:
                    has_next = page.locator('button:has-text("Next")').first.is_visible(timeout=5000)
                except Exception:
                    pass

                if has_next or 'create' in current_url.lower():
                    print(f"   Post creation dialog opened via input #{idx}!")
                    uploaded = True
                    break
                else:
                    # Check for any post-related UI
                    buttons_text = page.evaluate("""
                        Array.from(document.querySelectorAll('button')).map(b => b.textContent?.trim()).filter(Boolean)
                    """)
                    if any(t in ['Next', 'Share', 'Crop', 'Filter'] for t in buttons_text):
                        print(f"   Post creation detected via input #{idx}!")
                        uploaded = True
                        break

            except Exception as e:
                print(f"   Input #{idx} error: {e}")
                continue

    if not uploaded:
        print("   SKIP: Could not trigger post creation — no suitable file input worked")
        _debug_page(page, "POST UPLOAD FAILED")
        return

    # --- Step 3: Click Next (crop → filter → caption) ---
    for step_num, step_label in enumerate(["Crop → Filter", "Filter → Caption"], 1):
        print(f"   Step {step_num}: {step_label} — clicking Next...")
        human_delay(1, 2)

        if not _click_button_by_text(page, "Next"):
            print(f"   WARNING: Could not click Next for {step_label}")
            _debug_page(page, f"NEXT {step_num} FAILED")
        else:
            print(f"   Next clicked ({step_label})")

        human_delay(3, 5)

    _debug_page(page, "CAPTION SCREEN")

    # --- Step 4: Write caption ---
    print("   Writing caption...")
    selected_caption = random.choice(DEFAULT_CAPTIONS)
    caption_filled = False

    for selector in [
        'div[aria-label="Write a caption..."][contenteditable]',
        'textarea[aria-label="Write a caption..."]',
        'div[role="textbox"][contenteditable]',
        'div[contenteditable="true"]',
        'textarea[placeholder*="caption"]',
        'textarea[placeholder*="Caption"]',
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=3000):
                el.click()
                human_delay(0.5, 1)
                if 'contenteditable' in selector:
                    page.keyboard.type(selected_caption, delay=30)
                else:
                    el.fill(selected_caption)
                caption_filled = True
                print(f"   Caption: '{selected_caption}'")
                break
        except Exception:
            continue

    if not caption_filled:
        try:
            page.keyboard.type(selected_caption, delay=50)
            caption_filled = True
            print(f"   Caption (typed blind): '{selected_caption}'")
        except Exception:
            print("   WARNING: Could not fill caption — posting without caption")

    human_delay(1, 2)

    # --- Step 5: Click Share ---
    print("   Clicking Share...")
    if _click_button_by_text(page, "Share"):
        human_delay(8, 12)
        print("   Post shared successfully!")
    else:
        print("   WARNING: Could not click Share button")
        _debug_page(page, "SHARE FAILED")

    _debug_page(page, "POST DONE")


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
     12. Upload profile picture
     13. Create first post

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

            # Navigate to profile for pfp upload
            profile_url = f"https://www.instagram.com/{username}/"
            print(f"\nNavigating to profile: {profile_url}")
            page.goto(profile_url, timeout=NAV_TIMEOUT)
            human_delay(3, 5)

            profile_pic = _upload_profile_picture(page, context)

            # Navigate back to profile for post creation
            # (mobile web doesn't have Create Post on home — only stories)
            print(f"\nNavigating back to profile for post creation...")
            page.goto(profile_url, timeout=NAV_TIMEOUT)
            human_delay(3, 5)

            exclude_file = os.path.basename(profile_pic) if profile_pic else None
            _create_first_post(page, exclude_file)

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
