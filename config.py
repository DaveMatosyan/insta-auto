"""
Configuration settings for Instagram Account Generator
"""

# --- EMAIL CONFIGURATION ---
BASE_EMAIL_PREFIX = "test308test11"  # Will become gagikzugaran+100@gmail.com, gagikzugaran+101@gmail.com, etc.
EMAIL_DOMAIN = "@gmail.com"
START_NUMBER = 30  # Starting number for email suffix
NUM_ACCOUNTS = 1   # Number of accounts to create

# --- GMAIL CONFIGURATION FOR AUTOMATIC VERIFICATION CODE RETRIEVAL ---
# Choose between Gmail API (recommended - no CAPTCHA) or IMAP (requires App Password)
USE_GMAIL_API = True  # Set to True to use Gmail API (recommended), False for IMAP

# Gmail API Configuration
GMAIL_CREDENTIALS_FILE = "gmail_credentials.json"  # Download from Google Cloud Console

# Gmail IMAP Configuration (only used if USE_GMAIL_API = False)
# Get App Password from: https://myaccount.google.com/apppasswords

# --- PROXY CONFIGURATION ---
PROXIES_FILE = "proxies.json"
ACCOUNTS_PER_PROXY = 1

# --- DAILY FOLLOW CONFIGURATION ---
DAILY_FOLLOWS_PER_ACCOUNT = 5

# --- SESSION / LOG DIRS ---
SESSIONS_DIR = "sessions"
LOGS_DIR = "logs"

# --- TARGET SCRAPER CONFIGURATION ---
TARGET_CREATORS = [
    # --- Top OF girls with big Instagram presence (95%+ male commenters) ---
    "hannahowo",            # ~3M — cosplay/e-girl, OF link in bio
    "corinnakopf",          # ~7M — OF creator, gaming/lifestyle
    "iamyanetgarcia",       # ~15M — ex weather girl, lingerie/bikini
    "danielleyayalaa",      # ~5M — glamour/bikini, male-heavy
    "viki_odintcova",       # ~5M — Russian glamour model
    "soyneiva",             # ~5M — Colombian model, male-heavy
    "mathildtantot",        # ~10M — French model/influencer
    "anacheri",             # ~500K — gym/glamour model, OF creator
]
SCRAPER_MAX_POSTS = 12         # Posts to scrape per creator (more posts = more commenters)
SCRAPER_SCORE_PROFILES = True  # Visit each commenter profile to score quality
SCRAPER_MIN_SCORE = 4          # Minimum buyer-intent score (0-10) to keep a target
SCRAPER_OUTPUT_CSV = "csv_management/csv_files/targets_scored.csv"

# --- BANDWIDTH OPTIMIZATION ---
BLOCK_IMAGES = True  # Block image loading to minimize bandwidth (disabled during upload steps)

# --- TIMING CONFIGURATION ---
STOP_SEC = 3  # Pause between actions

# --- FILE CONFIGURATION ---
JSON_FILE = "instagram_accounts.json"  # File to save account info

# --- PROFILE AND POST CONFIGURATION ---
# Profile pic + post image are picked RANDOMLY from images/ folder (no hardcoded paths)
IMAGES_DIR = "images"  # Folder with images for profile pics and posts
POST_CAPTION = "Check me outtt! 📸"  # Caption for the post

