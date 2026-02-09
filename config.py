"""
Configuration settings for Instagram Account Generator
"""

# --- EMAIL CONFIGURATION ---
BASE_EMAIL_PREFIX = "gagikzugaran"  # Will become gagikzugaran+100@gmail.com, gagikzugaran+101@gmail.com, etc.
EMAIL_DOMAIN = "@gmail.com"
START_NUMBER = 1110  # Starting number for email suffix
NUM_ACCOUNTS = 10   # Number of accounts to create

# --- GMAIL CONFIGURATION FOR AUTOMATIC VERIFICATION CODE RETRIEVAL ---
# Choose between Gmail API (recommended - no CAPTCHA) or IMAP (requires App Password)
USE_GMAIL_API = True  # Set to True to use Gmail API (recommended), False for IMAP

# Gmail API Configuration
GMAIL_CREDENTIALS_FILE = "gmail_credentials.json"  # Download from Google Cloud Console

# Gmail IMAP Configuration (only used if USE_GMAIL_API = False)
# Get App Password from: https://myaccount.google.com/apppasswords

# --- TIMING CONFIGURATION ---
STOP_SEC = 3  # Pause between actions
VPN_CHANGE_INTERVAL = 3  # Change VPN every X accounts

# --- FILE CONFIGURATION ---
JSON_FILE = "instagram_accounts.json"  # File to save account info

# --- PROFILE AND POST CONFIGURATION ---
PROFILE_PIC_PATH = "images/profile.jpg"  # Path to profile picture (e.g., "images/profile.jpg") - Set to None to skip
POST_IMAGE_PATH = "images/post.png"   # Path to post image (e.g., "images/post.jpg") - Set to None to skip
POST_CAPTION = "Check me outtt! 📸"  # Caption for the post

# --- OPENVPN CONFIGURATION FOR WINDOWS ---
OPENVPN_PATH = r"C:\\Program Files\\OpenVPN\\bin\\openvpn.exe"  # Default OpenVPN install path
VPN_CONFIGS_DIR = r"C:\\Users\dvdma\\vpn_configs"  # Where you saved .ovpn files
VPN_CREDENTIALS_FILE = "vpn_credentials.txt"  # File with username and password

# --- VPN CONFIG FILES MAPPING ---
# Add your VPN config files here
VPN_CONFIG_FILES = {
    # "US": "us1.ovpn",
    # "UK": "uk1.ovpn",
    # "DE": "de1.ovpn",
}
