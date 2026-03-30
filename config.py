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
START_NUMBER = 1000001  # Starting number for email suffix (7 digits to avoid matching 6-digit verification codes)
NUM_ACCOUNTS = 1   # Number of accounts to create

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

# --- DM AUTOMATION CONFIGURATION ---
FANVUE_LINK = "https://link.me/aikorennn"  # Linktree deep link (in bio)

# Persona
DM_PERSONA_NAME = "Aiko Ren"
DM_PERSONA_AGE = 21
DM_PERSONA_LOCATION = "Los Angeles, CA"
DM_PERSONA_STUDIES = "Psychology"

# Conversation limits (7-stage system handles pitch timing automatically)
DM_MAX_MESSAGES_BEFORE_DEAD = 50   # Kill engaged lead after 50 messages if no conversion
DM_CONTEXT_SUMMARIZE_AFTER = 30    # Summarize old messages after 30 to save tokens

# Follow-back timing
DM_MIN_FOLLOWBACK_AGE_DAYS = 1     # Wait 1 day after follow before DMing
DM_MAX_FOLLOWBACK_AGE_DAYS = 7     # Don't DM if followed > 7 days ago

# Reply timing (seconds) — research: <1 min reply = 391% better conversion
DM_REPLY_ENGAGED = (15, 45)        # 15-45 sec: interested/sexual replies (fastest)
DM_REPLY_FAST = (30, 90)           # 30-90 sec: opening msgs, quick answers
DM_REPLY_NORMAL = (60, 180)        # 1-3 min: mid-conversation
DM_REPLY_SLOW = (180, 480)         # 3-8 min: playing cool after flirty msgs
DM_REPLY_AFTER_PITCH = (600, 1800) # 10-30 min: after sending Fanvue pitch

# Distraction pauses (replaces seen-zone mechanic)
DM_DISTRACTION_PAUSE_CHANCE = 0.15   # 15% chance of 5-15 min "distraction" pause
DM_DISTRACTION_PAUSE_SEC = (300, 900)  # 5-15 min pause range

# Activity hours — no DMs outside this window (account local time)
DM_ACTIVE_HOURS = (7, 23)  # 7am to 11pm

# DM rate limiting (conservative weekly ramp — research: max 20 cold DMs/day)
DM_RAMP_SCHEDULE = [
    (0,  3),     # Week 1: 3 DMs/day (warming up)
    (7,  5),     # Week 2: 5 DMs/day
    (14, 10),    # Week 3: 10 DMs/day
    (21, 15),    # Week 4: 15 DMs/day
    (30, 20),    # Month 2+: 20 DMs/day (safe ceiling for cold DMs)
]

# Timing between DM threads
DM_BETWEEN_THREADS_SEC = (60, 180)  # 1-3 min between different conversations

# Follow-up sequence — research: 3 attempts max per cold target
DM_MAX_COLD_ATTEMPTS = 3            # Max messages to unresponsive target before dead
DM_FOLLOWUP_1_AFTER_HOURS = 48      # Send follow-up #1 after 48h no reply
DM_FOLLOWUP_2_AFTER_HOURS = 24      # Send follow-up #2 after 24h no reply to #1

# Re-engagement (for targets who went cold after initial engagement)
DM_COLD_AFTER_HOURS = 48            # Mark as needing re-engagement after 48h silence
DM_DEAD_AFTER_HOURS = 72            # Mark as dead after 72h no reply to re-engagement
DM_REENGAGE_AFTER_DAYS = 14         # Try one more time after 2 weeks
