"""
Instagram account creation logic
"""

import time
import os
import re
from playwright.sync_api import sync_playwright
from config import BASE_EMAIL_PREFIX, EMAIL_DOMAIN, STOP_SEC, USE_GMAIL_API
from utils import generate_random_string, print_account_info
from account_storage import save_account

# Import Gmail method based on config
if USE_GMAIL_API:
    from gmail_api import authenticate_gmail_api, build_gmail_service, get_verification_code_from_gmail_api
else:
    import imaplib
    from config import GMAIL_EMAIL, GMAIL_PASSWORD


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
    
    with sync_playwright() as p:
        # 1. SETUP IPHONE PROFILE
        iphone = p.devices['iPhone 13']
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            **iphone,
            locale='en-US',
            timezone_id='America/Los_Angeles'
        )

        # 2. INJECT GPU SPOOFING
        context.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Apple Inc.';
                if (parameter === 37446) return 'Apple GPU';
                return getParameter(parameter);
            };
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
            # 4. NAVIGATE TO SIGNUP
            page.goto("https://www.instagram.com/accounts/signup/email/")
            time.sleep(4)

            # 5. SWITCH TO EMAIL VIEW (If Phone view loads first)
            try:
                switch_btn = page.locator('div[role="button"], button').filter(has_text="Sign up with email").first
                if switch_btn.is_visible():
                    print("Switching to Email view...")
                    switch_btn.click()
                    time.sleep(2)
            except:
                pass

            # 6. STEP 1: ENTER EMAIL ONLY
            try:
                print("Entering Email...")
                page.locator('input[aria-label="Email"]').fill(email)
                time.sleep(STOP_SEC)
                
                print("Clicking Next...")
                # Robust clicker
                try:
                    page.get_by_role("button", name="Next").first.click(timeout=3000)
                except:
                    page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
                
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
            time.sleep(5)
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
                time.sleep(STOP_SEC)
                
                print("Clicking Next...")
                try:
                    page.get_by_role("button", name="Next").first.click(timeout=3000)
                except:
                    page.locator('div[role="button"]:has-text("Next")').last.click(force=True)
            
            # 9. STEP 4: FILL PROFILE DETAILS (Name, Password)
            # This screen appears AFTER the code is verified
            print("Waiting for Profile Details screen...")
            time.sleep(5)
            
            try:
                # Sometimes it asks for Name/Pass, sometimes just Password first.
                # We try to fill whatever is visible.
                
                # Full Name
                if page.locator('input[aria-label="Full Name"]').is_visible():
                    print("Filling Full Name...")
                    page.locator('input[aria-label="Full Name"]').fill(fullname)
                    time.sleep(STOP_SEC)

                # Password (crucial)
                if page.locator('input[aria-label="Password"]').is_visible():
                    print("Filling Password...")
                    page.locator('input[aria-label="Password"]').fill(password)
                    time.sleep(STOP_SEC)
                
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

            except Exception as e:
                print(f"Error filling profile details: {e}")

            # 10. STEP 5: BIRTHDAY (FIXED)
            print("Waiting for Birthday screen...")
            time.sleep(5)
            try:
                # Instagram uses a date input field with type="date"
                # Set a birthdate that makes the user 18+ (e.g., 1998-01-15)
                print("Setting birthday...")
                
                # Look for the date input field
                birthday_input = page.locator('input[type="date"]').first
                
                if birthday_input.is_visible(timeout=5000):
                    # Set a valid birthdate (January 15, 1998 = ~28 years old)
                    birthday_input.fill("1998-01-15")
                    time.sleep(2)
                    print("Birthday set to: 1998-01-15")
                
                # Click Next
                time.sleep(STOP_SEC)
                print("Clicking Next...")
                page.locator('div[role="button"]:has-text("Next")').last.click()
                
            except Exception as e:
                 print(f"Birthday step error: {e}")
                 print("You may need to set the birthday manually in the browser.")

            # 11. STEP 6: FULL NAME PAGE
            print("Waiting for Full Name screen...")
            time.sleep(5)
            try:
                # Note: aria-label is "Full name" with lowercase 'n'
                fullname_input = page.locator('input[aria-label="Full name"]')
                if fullname_input.is_visible(timeout=5000):
                    print("Filling Full Name...")
                    # Click the input first to focus it
                    fullname_input.click()
                    time.sleep(0.5)
                    # Fill the fullname
                    fullname_input.fill(fullname)
                    time.sleep(3)
                    
                    print("Clicking Next...")
                    page.locator('div[role="button"]:has-text("Next")').last.click()
            except Exception as e:
                print(f"Full Name step error: {e}")

            # 12. STEP 7: USERNAME PAGE
            print("Waiting for Username screen...")
            time.sleep(5)
            try:
                username_input = page.locator('input[aria-label="Username"]')
                if username_input.is_visible(timeout=5000):
                    print("Filling Username...")
                    username_input.fill(username)
                    time.sleep(5)
                    
                    print("Clicking Next...")
                    page.locator('div[role="button"]:has-text("Next")').last.click()
            except Exception as e:
                print(f"Username step error: {e}")

            # 13. STEP 8: AGREE TO TERMS
            print("Waiting for Terms agreement screen...")
            time.sleep(5)
            try:
                # Look for "I agree" button
                agree_button = page.locator('div[role="button"][aria-label="I agree"]').first
                
                if agree_button.is_visible(timeout=5000):
                    print("Clicking 'I agree' button...")
                    agree_button.click()
                    time.sleep(2)
                else:
                    # Alternative selector if the first one doesn't work
                    page.locator('div[role="button"]:has-text("I agree")').first.click()
                    time.sleep(2)
                    
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

            # Save to JSON
            save_account(email, username, password)

            # Wait before closing to allow user to verify
            print("\nBrowser will remain open for 20 seconds.")
            print("You can now complete any remaining steps manually.")
            time.sleep(200)

            return True

        except Exception as e:
            print(f"\n❌ ERROR creating account: {e}")
            print("Browser will stay open for 30 seconds for inspection...")
            time.sleep(30)
            return False
            
        finally:
            browser.close()
