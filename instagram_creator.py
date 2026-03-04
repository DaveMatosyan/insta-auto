"""
Instagram account creation logic
"""

import time
import os
import re
import random
from playwright.sync_api import sync_playwright
from config import BASE_EMAIL_PREFIX, EMAIL_DOMAIN, STOP_SEC, USE_GMAIL_API, SESSIONS_DIR, BLOCK_IMAGES
from utils import generate_random_string, print_account_info, generate_browser_fingerprint, parse_proxy_url
from account_storage import save_account

# Import Gmail method based on config
if USE_GMAIL_API:
    from gmail_api import authenticate_gmail_api, build_gmail_service, get_verification_code_from_gmail_api
else:
    import imaplib
    from config import GMAIL_EMAIL, GMAIL_PASSWORD


# Default post captions for random selection
DEFAULT_CAPTIONS = [
    "Check me out! 📸",
    "Living my best life ✨",
    "Feeling good! 😊",
    "Just vibing 💫",
    "Smile more 😍",
    "Life is beautiful 🌟",
    "Blessed and grateful 🙏",
    "One hot day! 🔥",
    "Catch me if you can 😉",
    "Love this moment 💕",
    "Excited for what's ahead 🎉",
    "Making memories 📷",
    "Golden hour magic ✨",
    "Feeling myself 💪",
    "Living for moments like these 🌈",
    "Good vibes only ✌️",
    "Just being me 💯",
    "This is my life 🌺",
    "Taking it one day at a time 🌅",
    "Spreading positivity 💖",
]

# --- TIMING CONSTANTS (proxy-friendly timeouts, efficient delays) ---
NAV_TIMEOUT = 30000       # 30s for page.goto (proxy can be slow)
ELEMENT_TIMEOUT = 15000   # 15s for element waits
CLICK_TIMEOUT = 10000     # 10s for click timeouts


def human_delay(min_sec=1, max_sec=3):
    """Add random human-like delays between actions"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def get_random_image(image_dir=None, exclude_pattern=None):
    """
    Get a random image from the images directory

    Args:
        image_dir (str): Path to the images directory (defaults to './images')
        exclude_pattern (str): Pattern to exclude (e.g., filename or partial filename)

    Returns:
        str: Full path to random image, or None if no images found
    """
    try:
        # Use default images folder if not specified
        if image_dir is None:
            image_dir = os.path.join(os.path.dirname(__file__), 'images')

        if not os.path.exists(image_dir):
            print(f"⚠️ Images directory not found: {image_dir}")
            return None

        # Get list of valid image files
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        image_files = [
            f for f in os.listdir(image_dir)
            if os.path.isfile(os.path.join(image_dir, f)) and
            os.path.splitext(f)[1].lower() in valid_extensions
        ]

        # Filter out excluded files
        if exclude_pattern:
            image_files = [f for f in image_files if exclude_pattern.lower() not in f.lower()]

        if not image_files:
            print(f"⚠️ No image files found in {image_dir}" + (f" (excluding {exclude_pattern})" if exclude_pattern else ""))
            return None

        # Randomly select one
        selected_image = random.choice(image_files)
        full_path = os.path.join(image_dir, selected_image)
        print(f"📸 Randomly selected image: {selected_image}")
        return full_path

    except Exception as e:
        print(f"❌ Error getting random image: {e}")
        return None


def get_verification_code_wrapper(email_to_check, max_retries=15, retry_delay=3):
    """
    Wrapper function to retrieve verification code using API or IMAP

    Args:
        email_to_check (str): The email address (for reference)
        max_retries (int): Maximum attempts to find the code
        retry_delay (int): Seconds between retries

    Returns:
        str: The 6-digit verification code, or None if not found
    """
    if USE_GMAIL_API:
        # Use Gmail API (no CAPTCHA issues)
        try:
            print("🔌 Authenticating with Gmail API...")
            creds = authenticate_gmail_api()
            if not creds:
                print("❌ Failed to authenticate with Gmail API")
                return None

            service = build_gmail_service(creds)
            return get_verification_code_from_gmail_api(service, max_retries, retry_delay)
        except Exception as e:
            print(f"❌ Gmail API error: {e}")
            return None
    else:
        # Use IMAP (legacy)
        return get_verification_code_from_gmail_imap(email_to_check, max_retries, retry_delay)


def get_verification_code_from_gmail_imap(email_to_check, max_retries=12, retry_delay=5):
    """
    Retrieve Instagram verification code from Gmail inbox via IMAP

    Args:
        email_to_check (str): The email address to check for the code
        max_retries (int): Maximum attempts to find the code
        retry_delay (int): Seconds between retries

    Returns:
        str: The 6-digit verification code, or None if not found
    """
    try:
        print(f"\n🔍 Fetching verification code from Gmail (IMAP) for {email_to_check}...")
        print(f"Checking mailbox (max {max_retries} attempts)...\n")

        for attempt in range(max_retries):
            try:
                # Connect to Gmail IMAP server
                mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
                mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
                mail.select("INBOX")

                # Search for emails from Instagram
                status, messages = mail.search(None, 'FROM "Instagram" OR FROM "noreply@instagram.com"')

                if messages[0]:
                    # Get the latest email
                    email_ids = messages[0].split()[-10:]  # Get last 10 emails

                    for email_id in reversed(email_ids):
                        status, msg_data = mail.fetch(email_id, "(RFC822)")

                        if msg_data:
                            email_body = msg_data[0][1].decode('utf-8', errors='ignore').lower()

                            # Look for 6-digit code patterns
                            code_match = re.search(r'\b(\d{6})\b', email_body)

                            if code_match:
                                verification_code = code_match.group(1)
                                print(f"✓ Found verification code: {verification_code}")
                                mail.close()
                                mail.logout()
                                return verification_code

                mail.close()
                mail.logout()

                # Code not found yet, wait and retry
                if attempt < max_retries - 1:
                    print(f"⏳ Code not found yet. Attempt {attempt + 1}/{max_retries}")
                    print(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

            except imaplib.IMAP4.error as e:
                print(f"⚠️ Gmail connection error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        print(f"❌ Could not retrieve verification code after {max_retries} attempts")
        return None

    except Exception as e:
        print(f"❌ Error fetching verification code: {e}")
        return None



def create_account(email_number, proxy_url=None):
    """Create a single Instagram account

    Args:
        email_number (int): Email suffix number
        proxy_url (str): Proxy URL to route traffic through (optional)
    """
    email = f"{BASE_EMAIL_PREFIX}+{email_number}{EMAIL_DOMAIN}"

    # Generate completely random browser fingerprint for each account
    fingerprint = generate_browser_fingerprint()

    print(f"🎭 Generated Browser Fingerprint: {fingerprint['device_model']}")
    print(f"🔐 Timezone: {fingerprint.get('timezone', 'America/Los_Angeles')}")
    print(f"📱 User Agent: {fingerprint.get('user_agent', 'None')}")
    if proxy_url:
        print(f"🌐 Proxy: {proxy_url[:50]}...")

    with sync_playwright() as p:
        # Generate random screen resolution
        screen_width = random.choice([375, 390, 393, 412, 414, 430])
        screen_height = random.choice([812, 844, 851, 915, 896, 932])

        # 1. LAUNCH BROWSER WITH STEALTH MODE
        browser = p.chromium.launch(
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

        # 2. CREATE CONTEXT WITH COMPLETELY NEW FINGERPRINT
        ctx_kwargs = dict(
            viewport={'width': screen_width, 'height': screen_height},
            user_agent=fingerprint.get('user_agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15'),
            locale='en-US',
            timezone_id=fingerprint.get('timezone', 'America/Los_Angeles'),
            permissions=[],  # No permissions by default
            geolocation=None,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=random.choice([2, 3]),
            extra_http_headers={
                'Accept-Language': fingerprint.get('accept_language', 'en-US,en;q=0.9'),
            }
        )
        # Route through proxy if provided
        if proxy_url:
            ctx_kwargs["proxy"] = parse_proxy_url(proxy_url)

        context = browser.new_context(**ctx_kwargs)

        # Block images to save bandwidth (will be unrouted for upload steps)
        if BLOCK_IMAGES:
            context.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda route: route.abort())

        # 3. INJECT COMPREHENSIVE STEALTH SCRIPTS TO HIDE PLAYWRIGHT
        context.add_init_script("""
            // Completely hide Playwright/automation
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });

            // Hide headless detection
            Object.defineProperty(navigator, 'headless', {
                get: () => false,
            });

            // Chrome detection
            window.chrome = {
                runtime: {},
            };

            // Spoof plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Spoof languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // Fix permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Randomize WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Apple Inc.';
                if (parameter === 37446) return 'Apple GPU';
                return getParameter(parameter);
            };

            // Random canvas fingerprint
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function() {
                return originalToDataURL.call(this);
            };

            // Spoof media devices
            Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {
                value: async () => []
            });

            // Hide Phantom reference
            delete window.callPhantom;
            delete window.__phantom;
        """)

        page = context.new_page()

        # 3. GENERATE PROFILE DATA
        password = "Pass" + generate_random_string(8) + "!"
        fullname = "Aria Sky"
        username = "aria_sky_" + generate_random_string(5)

        print(f"\n{'='*60}")
        print(f"Creating account #{email_number}")
        if proxy_url:
            print(f"Proxy: {proxy_url[:50]}")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print(f"Full Name: {fullname}")
        print(f"Username: {username}")
        print(f"{'='*60}\n")

        try:
            # 4. NAVIGATE TO PHONE SIGNUP FIRST (simulate real flow)
            print("Step 1: Navigating to phone signup page...")
            page.goto("https://www.instagram.com/accounts/signup/phone/", timeout=NAV_TIMEOUT)
            human_delay(2, 4)

            # 4b. THEN NAVIGATE TO EMAIL SIGNUP
            print("Step 2: Navigating to email signup page...")
            page.goto("https://www.instagram.com/accounts/signup/email/", timeout=NAV_TIMEOUT)
            human_delay(3, 5)

            # 5. SWITCH TO EMAIL VIEW (If Phone view loads first)
            try:
                switch_btn = page.locator('div[role="button"], button').filter(has_text="Sign up with email").first
                if switch_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Switching to Email view...")
                    switch_btn.click()
                    human_delay(1, 2)
            except:
                pass

            # 6. STEP 1: ENTER EMAIL ONLY
            try:
                print("Entering Email...")
                page.locator('input[aria-label="Email"]').wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
                page.locator('input[aria-label="Email"]').fill(email)
                human_delay(1, 2)

                print("Clicking Next...")
                # Robust clicker
                try:
                    page.get_by_role("button", name="Next").first.click(timeout=CLICK_TIMEOUT)
                except:
                    page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
                human_delay(2, 4)

            except Exception as e:
                print(f"Error in Email step: {e}")

            # 7. STEP 2: AUTOMATIC CODE RETRIEVAL FROM GMAIL
            print("\n" + "="*60)
            print(f" RETRIEVING VERIFICATION CODE FROM GMAIL (API MODE)")
            print(f" Email: {email}")
            print("="*60)

            # Wait for the code input field to appear
            try:
                page.locator('input[aria-label="Confirmation code"]').wait_for(state="visible", timeout=20000)
            except:
                print("Warning: Code field didn't appear automatically. Continuing...")

            # Fetch verification code automatically from Gmail using API or IMAP
            # Wait for Instagram to actually send the email before checking
            print("⏳ Waiting 15s for Instagram to deliver the email...")
            time.sleep(15)
            verification_code = get_verification_code_wrapper(email, max_retries=30, retry_delay=10)

            if not verification_code:
                print("❌ Failed to retrieve verification code!")
                print("Browser will stay open for inspection...")
                time.sleep(30)
                return False

            # 8. STEP 3: SUBMIT CODE
            if verification_code:
                print(f"Entering code: {verification_code}")
                page.locator('input[aria-label="Confirmation code"]').fill(verification_code)
                human_delay(1, 2)

                print("Clicking Next...")
                try:
                    page.get_by_role("button", name="Next").first.click(timeout=CLICK_TIMEOUT)
                except:
                    page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
                human_delay(2, 4)

            # 9. STEP 4: FILL PROFILE DETAILS (Name, Password)
            # This screen appears AFTER the code is verified
            print("Waiting for Profile Details screen...")
            human_delay(4, 6)

            try:
                # Sometimes it asks for Name/Pass, sometimes just Password first.
                # We try to fill whatever is visible.

                # Full Name
                if page.locator('input[aria-label="Full Name"]').is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Filling Full Name...")
                    page.locator('input[aria-label="Full Name"]').fill(fullname)
                    human_delay(1, 2)

                # Password (crucial)
                if page.locator('input[aria-label="Password"]').is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Filling Password...")
                    page.locator('input[aria-label="Password"]').fill(password)
                    human_delay(1, 2)

                # Save Login Info checkbox (sometimes blocks the button)
                try:
                    page.locator('input[type="checkbox"]').check()
                except:
                    pass

                # Click Next/Sign Up
                print("Clicking Next/Sign Up...")
                try:
                     page.locator('div[role="button"]:has-text("Next")').last.click(timeout=CLICK_TIMEOUT)
                except:
                     page.locator('div[role="button"]:has-text("Sign up")').last.click(force=True)
                human_delay(2, 4)

            except Exception as e:
                print(f"Error filling profile details: {e}")

            # 10. STEP 5: BIRTHDAY (FIXED)
            print("Waiting for Birthday screen...")
            human_delay(4, 6)
            try:
                # Generate random birthday between 1997-2000
                year = random.randint(1997, 2000)
                month = random.randint(1, 12)
                day = random.randint(1, 28)  # Use day 1-28 to avoid month-specific issues
                random_birthday = f"{year:04d}-{month:02d}-{day:02d}"

                print(f"Setting random birthday: {random_birthday}")

                # Try method 1: Direct date input field
                birthday_input = page.locator('input[type="date"]').first

                if birthday_input.is_visible(timeout=ELEMENT_TIMEOUT):
                    birthday_input.fill(random_birthday)
                    human_delay(1, 2)
                    print(f"Birthday set to: {random_birthday}")
                else:
                    print("⚠️ Date input field not visible, trying alternative method...")

                    # Try method 2: Look for month/day/year separate fields
                    try:
                        # Try to find and fill individual month/day/year fields
                        month_input = page.locator('input[placeholder*="Month"], input[aria-label*="month"]').first
                        day_input = page.locator('input[placeholder*="Day"], input[aria-label*="day"]').first
                        year_input = page.locator('input[placeholder*="Year"], input[aria-label*="year"]').first

                        if month_input.is_visible():
                            month_input.fill(str(month))
                            human_delay(1, 2)
                        if day_input.is_visible():
                            day_input.fill(str(day))
                            human_delay(1, 2)
                        if year_input.is_visible():
                            year_input.fill(str(year))
                            human_delay(1, 2)
                        print(f"Birthday fields filled with: {month}/{day}/{year}")
                    except Exception as e:
                        print(f"⚠️ Could not fill individual birthday fields: {e}")
                        # Try method 3: JavaScript approach
                        try:
                            page.evaluate(f"""
                                document.querySelector('input[type="date"]').value = '{random_birthday}';
                                document.querySelector('input[type="date"]').dispatchEvent(new Event('change', {{ bubbles: true }}));
                            """)
                            print(f"Birthday set via JavaScript: {random_birthday}")
                        except:
                            print("⚠️ Could not set birthday - may need manual intervention")

                # Click Next
                human_delay(1, 2)
                print("Clicking Next...")
                page.locator('div[role="button"]:has-text("Next")').last.click()
                human_delay(2, 4)

            except Exception as e:
                 print(f"Birthday step error: {e}")
                 print("You may need to set the birthday manually in the browser.")

            # 11. STEP 6: FULL NAME PAGE
            print("Waiting for Full Name screen...")
            human_delay(4, 6)
            try:
                # Note: aria-label is "Full name" with lowercase 'n'
                fullname_input = page.locator('input[aria-label="Full name"]')
                if fullname_input.is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Filling Full Name...")
                    # Click the input first to focus it
                    fullname_input.click()
                    human_delay(1, 2)
                    # Fill the fullname
                    fullname_input.fill(fullname)
                    human_delay(1, 2)

                    print("Clicking Next...")
                    page.locator('div[role="button"]:has-text("Next")').last.click()
                    human_delay(2, 4)
            except Exception as e:
                print(f"Full Name step error: {e}")

            # 12. STEP 7: USERNAME PAGE
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

            # 13. STEP 8: AGREE TO TERMS
            print("Waiting for Terms agreement screen...")
            human_delay(4, 6)
            try:
                # Look for "I agree" button
                agree_button = page.locator('div[role="button"][aria-label="I agree"]').first

                if agree_button.is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Clicking 'I agree' button...")
                    agree_button.click()
                    human_delay(20, 25)
                else:
                    # Alternative selector if the first one doesn't work
                    page.locator('div[role="button"]:has-text("I agree")').first.click()
                    human_delay(20, 25)

                print("Terms accepted!")

            except Exception as e:
                print(f"Terms agreement error: {e}")
                print("You may need to click 'I agree' manually in the browser.")

            # 14. SUCCESS - SAVE ACCOUNT
            print("\n" + "="*60)
            print("🎉 ACCOUNT CREATION COMPLETE!")
            print("="*60)
            print(f"EMAIL: {email}")
            print(f"USERNAME: {username}")
            print(f"PASSWORD: {password}")
            print(f"FULL NAME: {fullname}")
            print("="*60)

            # Save to JSON with fingerprint and proxy
            save_account(email, username, password, fingerprint, proxy_url=proxy_url)

            # Save cookies for future session reuse
            try:
                os.makedirs(SESSIONS_DIR, exist_ok=True)
                cookie_path = os.path.join(SESSIONS_DIR, f"{username}_state.json")
                context.storage_state(path=cookie_path)
                print(f"🍪 Saved session cookies to {cookie_path}")
            except Exception as e:
                print(f"⚠️ Could not save cookies: {e}")

            # Increment START_NUMBER in config.py for next account
            try:
                config_path = os.path.join(os.path.dirname(__file__), 'config.py')
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_content = f.read()

                # Find and increment START_NUMBER
                import re
                match = re.search(r'START_NUMBER = (\d+)', config_content)
                if match:
                    current_num = int(match.group(1))
                    new_num = current_num + 1
                    updated_content = re.sub(r'START_NUMBER = \d+', f'START_NUMBER = {new_num}', config_content)

                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(updated_content)
                    print(f"✓ Updated START_NUMBER from {current_num} to {new_num}")
            except Exception as e:
                print(f"⚠️ Could not update START_NUMBER: {e}")

            # 15. CLOSE MODAL AND SKIP 3 TIMES
            print("\n📋 Handling onboarding modals...")
            human_delay(2, 3)

            # Click "Not Now" button if it appears
            try:
                not_now_btn = page.locator('div[role="button"]:has-text("Not Now")').first
                if not_now_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Clicking 'Not Now' button...")
                    not_now_btn.click()
                    human_delay(2, 3)
            except:
                print("⚠️ 'Not Now' button not found")

            try:
                # Try to close modal by clicking X button
                close_btn = page.locator('div[role="button"][aria-label="Close"]').first
                if close_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                    print("Closing modal...")
                    close_btn.click()
                    human_delay(1, 2)
            except:
                print("⚠️ No modal to close")

            # Skip 3 times
            for skip_i in range(3):
                try:
                    skip_btn = page.locator('div[role="button"]:has-text("Skip")').first
                    if skip_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                        print(f"Skipping step {skip_i + 1}/3...")
                        skip_btn.click()
                        human_delay(2, 3)
                    else:
                        print(f"Skip button not found for step {skip_i + 1}")
                        break
                except Exception as e:
                    print(f"⚠️ Could not skip: {e}")
                    break

            # 16. NAVIGATE TO PROFILE PAGE
            profile_url = f"https://www.instagram.com/{username}/"
            print(f"\n🔗 Navigating to profile: {profile_url}")
            page.goto(profile_url, timeout=NAV_TIMEOUT)
            human_delay(3, 5)
            # 17. UPLOAD PROFILE PICTURE
            # Unblock images for upload steps
            if BLOCK_IMAGES:
                context.unroute("**/*.{png,jpg,jpeg,gif,webp,svg}")

            print("\n📸 Uploading profile picture...")
            human_delay(2, 3)
            profile_pic = None
            try:
                profile_pic = get_random_image()

                if profile_pic:
                    print("Setting profile picture...")
                    # Try multiple file input approaches
                    file_inputs = page.locator('input[type="file"]')
                    input_count = file_inputs.count()
                    print(f"   Found {input_count} file input(s)")

                    uploaded = False
                    for idx in range(input_count):
                        try:
                            file_inputs.nth(idx).set_input_files(profile_pic)
                            human_delay(3, 5)
                            # Check if crop/save dialog appeared
                            save_btn = page.evaluate("""
                                Array.from(document.querySelectorAll('button')).find(
                                    b => ['Save', 'Done', 'Apply'].includes(b.textContent.trim())
                                )?.textContent
                            """)
                            if save_btn:
                                print(f"   Clicking '{save_btn}'...")
                                page.evaluate(f"""
                                    Array.from(document.querySelectorAll('button')).find(
                                        b => b.textContent.trim() === '{save_btn}'
                                    )?.click()
                                """)
                                human_delay(7, 9)
                                print("✅ Profile picture uploaded successfully!")
                                uploaded = True
                                break
                        except Exception:
                            continue

                    if not uploaded:
                        print("⚠️ Could not upload profile picture via file inputs")
                else:
                    print(f"⚠️ No profile picture image found in images folder")

            except Exception as e:
                print(f"⚠️ Error uploading profile picture: {e}")

            # 18. NAVIGATE TO INSTAGRAM HOME FOR POST CREATION
            print("\n🔗 Navigating to Instagram home to create post...")
            page.goto("https://www.instagram.com/", timeout=NAV_TIMEOUT)
            human_delay(5, 7)

            # 19. CREATE POST
            print("\n📝 Creating first post...")
            human_delay(2, 3)
            try:
                # Get post image, excluding the profile picture filename
                exclude_file = os.path.basename(profile_pic) if profile_pic else None
                post_image = get_random_image(exclude_pattern=exclude_file)

                if post_image:
                    # Click the New Post / Create button (try multiple selectors)
                    create_clicked = False
                    for label in ['New post', 'Create', 'Post']:
                        try:
                            btn = page.evaluate(f"""
                                (() => {{
                                    const svg = Array.from(document.querySelectorAll('svg[aria-label]')).find(
                                        s => s.getAttribute('aria-label') === '{label}'
                                    );
                                    if (svg) {{
                                        const link = svg.closest('a') || svg.closest('div[role="button"]') || svg.parentElement;
                                        if (link) {{ link.click(); return true; }}
                                    }}
                                    return false;
                                }})()
                            """)
                            if btn:
                                print(f"   Clicked '{label}' button")
                                create_clicked = True
                                break
                        except Exception:
                            continue

                    if not create_clicked:
                        print("⚠️ Could not find Create/Post button")

                    human_delay(3, 5)

                    # Upload image via file input
                    print("Uploading post image...")
                    page.locator('input[type="file"]').first.set_input_files(post_image)
                    human_delay(4, 6)

                    # Click Next (crop screen) — try button text + role
                    for step in ["1/2", "2/2"]:
                        print(f"Clicking Next ({step})...")
                        try:
                            next_btn = page.locator('div[role="button"]:has-text("Next")').first
                            if next_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                                next_btn.click()
                            else:
                                page.evaluate("Array.from(document.querySelectorAll('button, div[role=\"button\"]')).find(b => b.textContent.trim() === 'Next')?.click()")
                        except Exception:
                            page.evaluate("Array.from(document.querySelectorAll('button, div[role=\"button\"]')).find(b => b.textContent.trim() === 'Next')?.click()")
                        human_delay(3, 5)

                    # Write caption — try multiple selectors
                    print("Writing caption...")
                    selected_caption = random.choice(DEFAULT_CAPTIONS)
                    caption_filled = False
                    for selector in [
                        'textarea[aria-label="Write a caption…"]',
                        'textarea[aria-label="Write a caption..."]',
                        'div[aria-label="Write a caption..."][contenteditable]',
                        'div[aria-label="Write a caption…"][contenteditable]',
                        'div[role="textbox"][contenteditable]',
                        'textarea[placeholder*="caption"]',
                    ]:
                        try:
                            el = page.locator(selector).first
                            if el.is_visible(timeout=3000):
                                el.click()
                                human_delay(0.5, 1)
                                el.fill(selected_caption)
                                caption_filled = True
                                print(f"Caption: {selected_caption}")
                                break
                        except Exception:
                            continue

                    if not caption_filled:
                        # Last resort: type into whatever is focused
                        try:
                            page.keyboard.type(selected_caption, delay=50)
                            caption_filled = True
                            print(f"Caption (typed): {selected_caption}")
                        except Exception:
                            print("⚠️ Could not fill caption")

                    human_delay(1, 2)

                    # Click Share
                    print("Clicking Share...")
                    try:
                        share_btn = page.locator('div[role="button"]:has-text("Share")').first
                        if share_btn.is_visible(timeout=ELEMENT_TIMEOUT):
                            share_btn.click()
                        else:
                            page.evaluate("Array.from(document.querySelectorAll('button, div[role=\"button\"]')).find(b => b.textContent.trim() === 'Share')?.click()")
                    except Exception:
                        page.evaluate("Array.from(document.querySelectorAll('button, div[role=\"button\"]')).find(b => b.textContent.trim() === 'Share')?.click()")

                    human_delay(5, 8)
                    print("✅ Post created successfully!")
                else:
                    print(f"⚠️ No post image found in images folder")

            except Exception as e:
                print(f"⚠️ Error creating post: {e}")
            # 20. CLOSE BROWSER
            print("\n✅ All tasks completed! Closing browser...")
            human_delay(2, 3)

            return True

        except Exception as e:
            print(f"\n❌ ERROR creating account: {e}")
            print("Browser will stay open for 30 seconds for inspection...")
            time.sleep(30)
            return False

        browser.close()
