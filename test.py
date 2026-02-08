from playwright.sync_api import sync_playwright
import time
import random
import string
import json
import os
import subprocess

# --- CONFIGURATION ---
BASE_EMAIL_PREFIX = "gagikzugaran"  # Will become gagikzugaran+100@gmail.com, gagikzugaran+101@gmail.com, etc.
EMAIL_DOMAIN = "@gmail.com"
START_NUMBER = 1000  # Starting number for email suffix
NUM_ACCOUNTS = 10   # Number of accounts to create
STOP_SEC = 3
JSON_FILE = "instagram_accounts.json"  # File to save account info
VPN_CHANGE_INTERVAL = 3  # Change VPN every X accounts

# OPENVPN CONFIGURATION FOR WINDOWS
OPENVPN_PATH = r"C:\\Program Files\\OpenVPN\\bin\\openvpn.exe"  # Default OpenVPN install path
VPN_CONFIGS_DIR = r"C:\\Users\dvdma\\vpn_configs"  # Where you saved .ovpn files
VPN_CREDENTIALS_FILE = "vpn_credentials.txt"  # File with username and password


# Global variable to track OpenVPN process
openvpn_process = None

def generate_random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def load_accounts():
    """Load existing accounts from JSON file"""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    return json.loads(content)
        except json.JSONDecodeError:
            print(f"⚠️ Warning: {JSON_FILE} is corrupted, starting fresh")
            pass
    return []

def save_account(email, username, password):
    """Save account credentials to JSON file"""
    accounts = load_accounts()
    accounts.append({
        "email": email,
        "username": username,
        "password": password
    })
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved account to {JSON_FILE}")

def connect_openvpn(country):
    """Connect to OpenVPN using config file"""
    global openvpn_process
    
    try:
        # Get config file for country
        if country not in VPN_CONFIG_FILES:
            print(f"❌ No config file defined for {country}")
            return False
        
        config_file = VPN_CONFIG_FILES[country]
        config_path = os.path.join(VPN_CONFIGS_DIR, config_file)
        
        # Check if config file exists
        if not os.path.exists(config_path):
            print(f"❌ Config file not found: {config_path}")
            print(f"   Please download it from https://account.protonvpn.com/downloads")
            return False
        
        # Check if credentials file exists
        if not os.path.exists(VPN_CREDENTIALS_FILE):
            print(f"❌ Credentials file not found: {VPN_CREDENTIALS_FILE}")
            print("   Create a file with your OpenVPN username on line 1 and password on line 2")
            return False
        
        print(f"\n🔒 Connecting to OpenVPN ({country})...")
        print(f"   Config: {config_file}")
        
        # Build OpenVPN command
        cmd = [
            OPENVPN_PATH,
            "--config", config_path,
            "--auth-user-pass", VPN_CREDENTIALS_FILE,
            "--auth-nocache"
        ]
        
        # Start OpenVPN process (it runs in background)
        openvpn_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Wait for connection to establish
        print("⏳ Waiting for VPN connection to establish...")
        time.sleep(15)  # OpenVPN usually takes 10-15 seconds to connect
        
        # Check if process is still running (means connection succeeded)
        if openvpn_process.poll() is None:
            print("✓ OpenVPN process started successfully!")
            time.sleep(5)  # Extra time for connection to stabilize
            return True
        else:
            print("❌ OpenVPN process terminated unexpectedly")
            stdout, stderr = openvpn_process.communicate()
            print(f"Output: {stdout.decode()}")
            print(f"Error: {stderr.decode()}")
            return False
        
    except FileNotFoundError:
        print(f"❌ OpenVPN not found at: {OPENVPN_PATH}")
        print("   Please install OpenVPN from: https://openvpn.net/community-downloads/")
        return False
    except Exception as e:
        print(f"❌ Error connecting to OpenVPN: {e}")
        return False

def disconnect_openvpn():
    """Disconnect from OpenVPN"""
    global openvpn_process
    
    try:
        if openvpn_process and openvpn_process.poll() is None:
            print("\n🔓 Disconnecting from OpenVPN...")
            openvpn_process.terminate()
            time.sleep(3)
            
            # Force kill if still running
            if openvpn_process.poll() is None:
                openvpn_process.kill()
                time.sleep(2)
            
            print("✓ OpenVPN disconnected!")
            openvpn_process = None
        else:
            print("⚠️ No active OpenVPN connection")
            
    except Exception as e:
        print(f"⚠️ Error disconnecting OpenVPN: {e}")

def get_current_ip():
    """Get current IP address to verify VPN"""
    try:
        # Try multiple IP checking services
        services = [
            "curl -s ifconfig.me",
            "curl -s icanhazip.com",
            "curl -s api.ipify.org"
        ]
        
        for service in services:
            try:
                result = subprocess.run(service, shell=True, capture_output=True, text=True, timeout=10)
                ip = result.stdout.strip()
                if ip and '.' in ip:  # Basic validation
                    print(f"📍 Current IP: {ip}")
                    return ip
            except:
                continue
        
        print("⚠️ Could not retrieve IP from any service")
        return None
        
    except Exception as e:
        print(f"⚠️ Could not get IP: {e}")
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
        fullname = "Alex " + generate_random_string(4)
        username = "user" + generate_random_string(6)

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
            page.goto("https://www.instagram.com/accounts/emailsignup/")
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

            # 7. STEP 2: MANUAL CODE ENTRY
            print("\n" + "="*40)
            print(f" CHECK YOUR GMAIL ({email}) NOW!")
            print("="*40)
            
            # Wait for the code input field to actually appear
            try:
                page.locator('input[aria-label="Confirmation code"]').wait_for(state="visible", timeout=10000)
            except:
                print("Warning: Code field didn't appear automatically. Check browser.")

            # --- PAUSE FOR USER INPUT ---
            verification_code = input(">>> TYPE THE 6-DIGIT CODE HERE: ")
            # ----------------------------

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
            time.sleep(20)

            return True

        except Exception as e:
            print(f"\n❌ ERROR creating account: {e}")
            print("Browser will stay open for 30 seconds for inspection...")
            time.sleep(30)
            return False
            
        finally:
            browser.close()

def main():
    print("="*60)
    print(f"Base email: {BASE_EMAIL_PREFIX}+XXX{EMAIL_DOMAIN}")
    print(f"Starting number: {START_NUMBER}")
    print(f"Number of accounts to create: {NUM_ACCOUNTS}")
    print(f"VPN change interval: Every {VPN_CHANGE_INTERVAL} accounts")
    print(f"OpenVPN path: {OPENVPN_PATH}")
    print(f"Config directory: {VPN_CONFIGS_DIR}")
    print(f"Accounts will be saved to: {JSON_FILE}")
    print("="*60 + "\n")
    
    # Check initial IP
    print("\n📍 Checking initial IP address (without VPN)...")
    initial_ip = get_current_ip()
    
    successful = 0
    failed = 0
    current_country_index = 0
    
    for i in range(NUM_ACCOUNTS):
        email_number = START_NUMBER + i
        
        # Create account
        print(f"\n\n{'#'*60}")
        print(f"CREATING ACCOUNT {i+1}/{NUM_ACCOUNTS}")
        print(f"{'#'*60}\n")
        
        # Show current connection status
        print("📊 Current Connection Status:")
        
        if create_account(email_number):
            successful += 1
        else:
            failed += 1
            retry = input(f"\nAccount {email_number} failed. Retry? (y/n): ").lower()
            if retry == 'y':
                if create_account(email_number):
                    successful += 1
                    failed -= 1
        
        # Wait between accounts (except for the last one)
        if i < NUM_ACCOUNTS - 1:
            print(f"\n⏳ Waiting 10 seconds before next account...")
            time.sleep(10)
    
    # Disconnect VPN after all accounts are created
    print("\n" + "="*60)
    print("ALL ACCOUNTS CREATED - DISCONNECTING VPN")
    print("="*60)
    disconnect_openvpn()
    
    # Verify disconnection
    time.sleep(3)
    final_ip = get_current_ip()
    if final_ip == initial_ip:
        print(f"✅ VPN disconnected successfully (IP restored to {initial_ip})")
    else:
        print(f"⚠️ IP may still be different: {final_ip} vs {initial_ip}")
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Total accounts attempted: {NUM_ACCOUNTS}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"VPN locations used: {current_country_index}")
    print(f"All account info saved to: {JSON_FILE}")
    print("="*60 + "\n")

main()