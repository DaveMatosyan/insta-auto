"""
Instagram account creation logic
"""

import time
import os
import re
import random
from playwright.sync_api import sync_playwright
from config import BASE_EMAIL_PREFIX, EMAIL_DOMAIN, STOP_SEC, USE_GMAIL_API
from utils import generate_random_string, print_account_info, generate_browser_fingerprint
from account_storage import save_account

# Import Gmail method based on config
if USE_GMAIL_API:
    from gmail_api import authenticate_gmail_api, build_gmail_service, get_verification_code_from_gmail_api
else:
    import imaplib
    from config import GMAIL_EMAIL, GMAIL_PASSWORD


def human_delay(min_sec=1, max_sec=3):
    """Add random human-like delays between actions"""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def upload_profile_picture(page, image_path):
    """
    Upload a profile picture to Instagram account
    
    Args:
        page: Playwright page object
        image_path (str): Path to the image file
        
    Returns:
        bool: True if upload successful, False otherwise
    """
    try:
        if not os.path.exists(image_path):
            print(f"⚠️ Profile picture not found at: {image_path}")
            return False
        
        print("\n📸 Uploading profile picture...")
        
        # Navigate to profile
        page.goto("https://www.instagram.com/")
        time.sleep(3)
        
        # Click on profile icon (usually in bottom right or top left)
        try:
            profile_btn = page.locator('svg[aria-label="Profile"]').first
            profile_btn.click()
            time.sleep(2)
        except:
            # Alternative: navigate directly to profile
            page.goto("https://www.instagram.com/")
            time.sleep(2)
        
        # Click edit profile button
        try:
            edit_profile_btn = page.locator('div[role="button"]:has-text("Edit profile")').first
            if edit_profile_btn.is_visible(timeout=5000):
                edit_profile_btn.click()
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ Could not find edit profile button: {e}")
            return False
        
        # Click on profile picture to upload
        try:
            # Look for the profile picture area
            pic_upload = page.locator('div[role="button"]').filter(has_text="Change profile photo").first
            if pic_upload.is_visible(timeout=3000):
                pic_upload.click()
                time.sleep(1)
        except:
            pass
        
        # Handle file input
        try:
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(image_path)
            time.sleep(2)
            print("✓ Profile picture uploaded successfully!")
            return True
        except Exception as e:
            print(f"⚠️ Error uploading profile picture: {e}")
            return False
            
    except Exception as e:
        print(f"⚠️ Error in profile picture upload: {e}")
        return False


def create_post(page, post_image_path, caption=""):
    """
    Create a new post on Instagram
    
    Args:
        page: Playwright page object
        post_image_path (str): Path to the image for the post
        caption (str): Caption for the post
        
    Returns:
        bool: True if post created successfully, False otherwise
    """
    try:
        if not os.path.exists(post_image_path):
            print(f"⚠️ Post image not found at: {post_image_path}")
            return False
        
        print("\n📝 Creating new post...")
        
        # Navigate to Instagram home
        page.goto("https://www.instagram.com/")
        time.sleep(3)
        
        # Click on create/new post button (usually a + icon)
        try:
            create_btn = page.locator('svg[aria-label="Create"]').first
            create_btn.click()
            time.sleep(2)
        except:
            print("⚠️ Could not find create button")
            return False
        
        # Click on "Select from computer"
        try:
            select_btn = page.locator('div[role="button"]:has-text("Select from computer")').first
            if select_btn.is_visible(timeout=5000):
                select_btn.click()
                time.sleep(1)
        except:
            pass
        
        # Upload image
        try:
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(post_image_path)
            time.sleep(3)
            print("✓ Image selected for post")
        except Exception as e:
            print(f"⚠️ Error selecting post image: {e}")
            return False
        
        # Click Next button
        try:
            next_btn = page.locator('div[role="button"]:has-text("Next")').first
            if next_btn.is_visible(timeout=5000):
                next_btn.click()
                time.sleep(2)
        except:
            pass
        
        # Click Next again (for filters/editing)
        try:
            next_btn = page.locator('div[role="button"]:has-text("Next")').first
            if next_btn.is_visible(timeout=5000):
                next_btn.click()
                time.sleep(2)
        except:
            pass
        
        # Add caption if provided
        if caption:
            try:
                caption_field = page.locator('textarea[aria-label="Write a caption..."]').first
                if caption_field.is_visible(timeout=3000):
                    caption_field.click()
                    time.sleep(1)
                    caption_field.fill(caption)
                    time.sleep(1)
                    print(f"✓ Caption added: {caption}")
            except Exception as e:
                print(f"⚠️ Error adding caption: {e}")
        
        # Click Share button
        try:
            share_btn = page.locator('div[role="button"]:has-text("Share")').first
            if share_btn.is_visible(timeout=5000):
                share_btn.click()
                time.sleep(3)
                print("✓ Post created successfully!")
                return True
        except Exception as e:
            print(f"⚠️ Error sharing post: {e}")
            return False
            
    except Exception as e:
        print(f"⚠️ Error creating post: {e}")
        return False






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



def create_account(email_number, use_vpn_country=None):
    """Create a single Instagram account"""
    email = f"{BASE_EMAIL_PREFIX}+{email_number}{EMAIL_DOMAIN}"
    
    # Generate completely random browser fingerprint for each account
    fingerprint = generate_browser_fingerprint()
    
    print(f"🎭 Generated Browser Fingerprint: {fingerprint['device_model']}")
    print(f"🔐 Timezone: {fingerprint.get('timezone', 'America/Los_Angeles')}")
    print(f"📱 User Agent: {fingerprint.get('user_agent', 'None')}")
    
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
        context = browser.new_context(
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
        username = "ariasky" + generate_random_string(5)

        print(f"\n{'='*60}")
        print(f"Creating account #{email_number}")
        if use_vpn_country:
            print(f"VPN Location: {use_vpn_country}")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print(f"Full Name: {fullname}")
        print(f"Username: {username}")
        print(f"{'='*60}\n")

        try:
            # 4. NAVIGATE TO PHONE SIGNUP FIRST (simulate real flow)
            print("Step 1: Navigating to phone signup page...")
            page.goto("https://www.instagram.com/accounts/signup/phone/")
            human_delay(2, 4)
            
            # 4b. THEN NAVIGATE TO EMAIL SIGNUP
            print("Step 2: Navigating to email signup page...")
            page.goto("https://www.instagram.com/accounts/signup/email/")
            human_delay(3, 5)

            # 5. SWITCH TO EMAIL VIEW (If Phone view loads first)
            try:
                switch_btn = page.locator('div[role="button"], button').filter(has_text="Sign up with email").first
                if switch_btn.is_visible():
                    print("Switching to Email view...")
                    switch_btn.click()
                    human_delay(1, 2)
            except:
                pass

            # 6. STEP 1: ENTER EMAIL ONLY
            try:
                print("Entering Email...")
                page.locator('input[aria-label="Email"]').fill(email)
                human_delay(1, 2)
                
                print("Clicking Next...")
                # Robust clicker
                try:
                    page.get_by_role("button", name="Next").first.click(timeout=3000)
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
                page.locator('input[aria-label="Confirmation code"]').wait_for(state="visible", timeout=10000)
            except:
                print("Warning: Code field didn't appear automatically. Continuing...")
            
            # Fetch verification code automatically from Gmail using API or IMAP
            # Short delay to let Gmail deliver the email, then auto-retrieve
            human_delay(4, 6)
            verification_code = get_verification_code_wrapper(email, max_retries=15, retry_delay=3)
            
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
                    page.get_by_role("button", name="Next").first.click(timeout=3000)
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
                if page.locator('input[aria-label="Full Name"]').is_visible():
                    print("Filling Full Name...")
                    page.locator('input[aria-label="Full Name"]').fill(fullname)
                    human_delay(1, 2)

                # Password (crucial)
                if page.locator('input[aria-label="Password"]').is_visible():
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
                     page.locator('div[role="button"]:has-text("Next")').last.click(timeout=3000)
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
                
                if birthday_input.is_visible(timeout=5000):
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
                            human_delay(0.5, 1)
                        if day_input.is_visible():
                            day_input.fill(str(day))
                            human_delay(0.5, 1)
                        if year_input.is_visible():
                            year_input.fill(str(year))
                            human_delay(0.5, 1)
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
                if fullname_input.is_visible(timeout=5000):
                    print("Filling Full Name...")
                    # Click the input first to focus it
                    fullname_input.click()
                    human_delay(0.5, 1)
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
                if username_input.is_visible(timeout=5000):
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
                
                if agree_button.is_visible(timeout=5000):
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

            # Save to JSON with fingerprint
            save_account(email, username, password, fingerprint)

            # 15. CLOSE MODAL AND SKIP 3 TIMES
            print("\n📋 Closing modal and skipping onboarding steps...")
            human_delay(2, 3)
            
            try:
                # Try to close modal by clicking X button
                close_btn = page.locator('div[role="button"][aria-label="Close"]').first
                if close_btn.is_visible(timeout=3000):
                    print("Closing modal...")
                    close_btn.click()
                    human_delay(1, 2)
            except:
                print("⚠️ No modal to close")
            
            # Skip 3 times
            for skip_i in range(3):
                try:
                    skip_btn = page.locator('div[role="button"]:has-text("Skip")').first
                    if skip_btn.is_visible(timeout=3000):
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
            page.goto(profile_url)
            human_delay(3, 5)
            
            # 17. UPLOAD PROFILE PICTURE
            print("\n📸 Uploading profile picture...")
            human_delay(2, 3)
            try:
                # Get profile picture path
                images_dir = os.path.join(os.path.dirname(__file__), 'images')
                profile_pic = os.path.join(images_dir, 'profile.jpg')
                
                if os.path.exists(profile_pic):
                    # Click on profile picture area to upload
                    try:
                        # Try to click on the profile picture
                        pic_area = page.locator('button[aria-label*="profile photo"]').first
                        pic_area.click(force=True)
                        human_delay(1, 2)
                    except:
                        # Alternative: look for edit profile button
                        try:
                            edit_btn = page.locator('a:has-text("Edit profile"), div[role="button"]:has-text("Edit profile")').first
                            if edit_btn.is_visible(timeout=3000):
                                edit_btn.click()
                                human_delay(2, 3)
                            
                            # Then click profile picture area
                            pic_btn = page.locator('button:has-text("Change profile photo")').first
                            pic_btn.click()
                            human_delay(1, 2)
                        except:
                            print("⚠️ Could not find profile picture upload area")
                    
                    # Upload file
                    try:
                        file_input = page.locator('input[type="file"]').first
                        file_input.set_input_files(profile_pic)
                        human_delay(2, 3)
                        
                        # Click any confirm/save buttons
                        try:
                            save_btn = page.locator('button:has-text("Save")').first
                            if save_btn.is_visible(timeout=3000):
                                save_btn.click()
                                human_delay(2, 3)
                        except:
                            pass
                        
                        print("✅ Profile picture uploaded successfully!")
                    except Exception as e:
                        print(f"⚠️ Error uploading profile picture: {e}")
                else:
                    print(f"⚠️ Profile picture not found at {profile_pic}")
            except Exception as e:
                print(f"⚠️ Error in profile picture upload: {e}")
            
            # 18. RETURN TO PROFILE PAGE
            print(f"\n🔗 Returning to profile page: {profile_url}")
            page.goto(profile_url)
            human_delay(3, 5)
            
            # 19. CREATE POST
            print("\n📝 Creating first post...")
            human_delay(2, 3)
            try:
                # Get post image path
                images_dir = os.path.join(os.path.dirname(__file__), 'images')
                post_image = os.path.join(images_dir, 'post.png')
                
                if os.path.exists(post_image):
                    # Click create button from profile page
                    try:
                        create_btn = page.locator('svg[aria-label="Create"]').first
                        create_btn.click()
                        human_delay(2, 3)
                    except:
                        print("⚠️ Could not find create button")
                        raise
                    
                    # Select from computer
                    try:
                        select_btn = page.locator('div[role="button"]:has-text("Select from computer")').first
                        if select_btn.is_visible(timeout=3000):
                            select_btn.click()
                            human_delay(1, 2)
                    except:
                        pass
                    
                    # Upload image
                    try:
                        file_input = page.locator('input[type="file"]').first
                        file_input.set_input_files(post_image)
                        human_delay(3, 4)
                    except Exception as e:
                        print(f"⚠️ Error uploading post image: {e}")
                        raise
                    
                    # Click Next
                    try:
                        next_btn = page.locator('div[role="button"]:has-text("Next")').first
                        if next_btn.is_visible(timeout=3000):
                            next_btn.click()
                            human_delay(2, 3)
                    except:
                        pass
                    
                    # Click Next again (filters)
                    try:
                        next_btn = page.locator('div[role="button"]:has-text("Next")').first
                        if next_btn.is_visible(timeout=3000):
                            next_btn.click()
                            human_delay(2, 3)
                    except:
                        pass
                    
                    # Share post
                    try:
                        share_btn = page.locator('div[role="button"]:has-text("Share")').first
                        if share_btn.is_visible(timeout=3000):
                            share_btn.click()
                            human_delay(3, 4)
                            print("✅ Post created successfully!")
                        else:
                            print("⚠️ Could not find share button")
                    except Exception as e:
                        print(f"⚠️ Error sharing post: {e}")
                else:
                    print(f"⚠️ Post image not found at {post_image}")
            except Exception as e:
                print(f"⚠️ Error creating post: {e}")
            
            # 18. CLOSE BROWSER
            print("\n✅ All tasks completed! Closing browser...")
            human_delay(2, 3)

            return True

        except Exception as e:
            print(f"\n❌ ERROR creating account: {e}")
            print("Browser will stay open for 30 seconds for inspection...")
            time.sleep(30)
            return False
            
        finally:
            browser.close()
