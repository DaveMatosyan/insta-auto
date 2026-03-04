"""
Configuration settings for Instagram Account Generator
"""

# --- EMAIL CONFIGURATION ---
BASE_EMAIL_PREFIX = "test308test11"  # Will become gagikzugaran+100@gmail.com, gagikzugaran+101@gmail.com, etc.
EMAIL_DOMAIN = "@gmail.com"
START_NUMBER = 25  # Starting number for email suffix
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
    # Mid-tier fitness / glamour / bikini models (100K-1M followers)
    # Their comment sections are full of engaged male followers
    "lauraliechap",         # 747K — IFBB Bikini Pro
    "caileylonnie",         # 628K — swimsuit/bikini model
    "whitneyjohns",         # 765K — fitness coach
    "rebekahlea_fitness",   # 434K — fitness model
    "daniellejjackson",     # 410K — fitness / mental health
    "simonevillar",         # 361K — bikini model
    "rena_serenaa",         # 242K — powerlifter
    "jenronfit",            # 179K — IFBB Bikini Pro
    "jibinpark_",           # 162K — Olympian bikini/figure
    "jessicareneefit",      # 160K — IFBB Bikini Pro, vegan
    "thephillyfitchick",    # 153K — fitness model / actress
    "christinavargas",      # 148K — fitness model
    "sandraahorvath",       # 131K — bikini body athlete
    "cory_fit",             # 117K — health/performance coach
    "nikki_trinidad_",      # 102K — bikini model, LA
    # Larger accounts with heavy male engagement
    "anacheri",             # ~500K — fitness / model / gym owner
    "yanetegarcia",         # ~14M — ex weather girl / fitness
    "nicolemejia",          # ~500K — fitness educator
    "whitneysimmons",       # ~4M — fitness / Gymshark athlete
    "tammyhembrow",         # ~17M — fitness / activewear brand
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
PROFILE_PIC_PATH = "images/profile.jpg"  # Path to profile picture (e.g., "images/profile.jpg") - Set to None to skip
POST_IMAGE_PATH = "images/post.png"   # Path to post image (e.g., "images/post.jpg") - Set to None to skip
POST_CAPTION = "Check me outtt! 📸"  # Caption for the post

