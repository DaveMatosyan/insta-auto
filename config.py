"""
Configuration settings for Instagram Account Generator

All paths are absolute — derived from PROJECT_ROOT so that imports
from any subdirectory (core/, scraper/, etc.) resolve correctly.
"""

import os

# --- PROJECT ROOT (absolute) ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- LOAD .env file (secrets — never committed to git) ---
_env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# --- API KEYS (loaded from .env) ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# --- EMAIL CONFIGURATION ---
BASE_EMAIL_PREFIX = "redditakk4"  # Will become redditakk4+1100@gmail.com, redditakk4+1101@gmail.com, etc.
EMAIL_DOMAIN = "@gmail.com"
START_NUMBER = 1120  # Starting number for email suffix
NUM_ACCOUNTS = 9   # Number of accounts to create

# --- GMAIL CONFIGURATION FOR AUTOMATIC VERIFICATION CODE RETRIEVAL ---
# Choose between Gmail API (recommended - no CAPTCHA) or IMAP (requires App Password)
USE_GMAIL_API = True  # Set to True to use Gmail API (recommended), False for IMAP

# Gmail API Configuration
GMAIL_CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "gmail_credentials.json")

# Gmail IMAP Configuration (only used if USE_GMAIL_API = False)
# Get App Password from: https://myaccount.google.com/apppasswords

# --- PROXY CONFIGURATION ---
PROXIES_FILE = os.path.join(PROJECT_ROOT, "proxies.json")
ACCOUNTS_PER_PROXY = 1

# --- SESSION / LOG / DATA DIRS ---
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

# --- TARGET SCRAPER CONFIGURATION ---
TARGET_CREATORS = [
    # --- Already scraped (done) ---
    # "hannahowo",            # ~3M -- PRIVATE, 0 results
    # "corinnakopf",          # ~7M -- scraped, 208 leads
    # "iamyanetgarcia",       # ~15M -- scraped
    # "danielleyayalaa",      # ~5M -- scraped, 323 raw
    # "viki_odintcova",       # ~5M -- scraped, 211 raw
    # "soyneiva",             # ~5M -- scraped, 370 raw
    # "mathildtantot",        # ~10M -- scraped, 413 raw
    # "anacheri",             # ~500K -- scraped, 352 raw
    # --- Batch 2 — new creators ---
    "laurenwolfe",              # ~2M -- fitness/glamour
    "valentinanappi",           # ~8M -- adult model, huge male audience
    "demirose",                 # ~20M -- glamour model, bikini
    "niaborealiss",             # ~4M -- Brazilian model
    "lfrancescasofia",          # ~3M -- Italian model/influencer
    "amberhayes_",              # ~1M -- fitness/OF model
    "yanet_garcia",             # ~16M -- fitness/lifestyle
    "galfrancescaa",            # ~2M -- Italian glamour
    "polina_malinovskaya",      # ~6M -- Russian model
    "sveta_bilyalova",          # ~7M -- Russian glamour model
    "lindaperea_",              # ~3M -- Colombian model
    "kyliejenner",              # ~400M -- massive audience, lots of male commenters
    "iamhalsey",                # ~30M -- music/lifestyle
    "mikirai_",                 # ~2M -- Japanese model
    "sophiet",                  # ~10M -- actress, male-heavy
]
SCRAPER_MAX_POSTS = 12         # Posts to scrape per creator (more posts = more commenters)
SCRAPER_SCORE_PROFILES = True  # Visit each commenter profile to score quality
SCRAPER_MIN_SCORE = 4          # Minimum buyer-intent score (0-10) to keep a target
# (targets are now stored in Supabase `targets_scored` table)

# --- BANDWIDTH OPTIMIZATION ---
BLOCK_IMAGES = True  # Block image loading to minimize bandwidth (disabled during upload steps)

# --- TIMING CONFIGURATION ---
STOP_SEC = 3  # Pause between actions

# --- FILE CONFIGURATION ---
# Accounts are now stored in Supabase (table: accounts)

# --- PROFILE AND POST CONFIGURATION ---
# Profile pic + post image are picked RANDOMLY from data/images/ folder (no hardcoded paths)
POST_CAPTION = "Check me outtt!"
