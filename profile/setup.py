"""
Profile setup — upload posts, set bio, add linktree link.
Uses Playwright browser sessions for all operations.
Run once per account to make profiles look credible before DM outreach.
"""

import os
import random
import time

from config import (
    PROJECT_ROOT,
    SESSIONS_DIR,
    FANVUE_LINK,
    DM_PERSONA_NAME,
    DM_PERSONA_AGE,
    DM_PERSONA_LOCATION,
    DM_PERSONA_STUDIES,
)
from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.browser_profile import update_bio, upload_profile_pic, upload_post

# Directory with profile images to upload
PROFILE_IMAGES_DIR = os.path.join(PROJECT_ROOT, "data", "profile_images")

# Bio templates — randomly pick one per account
BIO_TEMPLATES = [
    f"{DM_PERSONA_AGE} LA | {DM_PERSONA_STUDIES.lower()} student | link below",
    f"{DM_PERSONA_LOCATION}\n{DM_PERSONA_STUDIES.lower()} major | {DM_PERSONA_AGE}\nlink in bio",
    f"{DM_PERSONA_AGE} | LA girl\nstudying {DM_PERSONA_STUDIES.lower()}\nlink in bio",
    f"{DM_PERSONA_LOCATION}\n{DM_PERSONA_AGE} | content creator",
]

# Post captions
POST_CAPTIONS = ["", "", "", "feeling cute", "good vibes only", "", "hiiii", "", ""]


def get_profile_images():
    """Get list of available profile images."""
    if not os.path.exists(PROFILE_IMAGES_DIR):
        os.makedirs(PROFILE_IMAGES_DIR, exist_ok=True)
        return []
    images = []
    for f in sorted(os.listdir(PROFILE_IMAGES_DIR)):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            images.append(os.path.join(PROFILE_IMAGES_DIR, f))
    return images


def setup_account_profile(account, linktree_url=None, num_posts=6, **kwargs):
    """
    Full profile setup for one account via browser.
    """
    username = account.get("username", "???")
    print(f"\n{'='*40}")
    print(f"Setting up profile for @{username}")
    print(f"{'='*40}")

    images = get_profile_images()
    if not images and num_posts > 0:
        print("[profile] No images in data/profile_images/ -- add photos and re-run")

    session = None
    results = {"bio": False, "posts": 0}

    try:
        session = open_session(account, headless=True, block_images=False)

        if not ensure_logged_in(session):
            print(f"  [profile] Could not log in @{username} -- skipping")
            return results

        page = session.page

        # 1. Update bio
        bio = random.choice(BIO_TEMPLATES)
        results["bio"] = update_bio(page, bio, linktree_url)

        # 2. Upload posts
        if images and num_posts > 0:
            selected = random.sample(images, min(num_posts, len(images)))
            for img in selected:
                caption = random.choice(POST_CAPTIONS)
                if upload_post(page, img, caption):
                    results["posts"] += 1
                time.sleep(random.uniform(15, 30))
        else:
            print("  [profile] Skipping posts (0 images)")

    except Exception as e:
        print(f"  [profile] Error setting up @{username}: {e}")

    finally:
        if session:
            close_session(session)

    print(f"\n[profile] @{username} done: bio={'OK' if results['bio'] else 'FAIL'}, posts={results['posts']}")
    return results


def setup_all_profiles(linktree_url=None, num_posts=6, **kwargs):
    """Run profile setup for all follow accounts."""
    accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]

    print(f"\n{'='*60}")
    print(f"PROFILE SETUP -- {len(accounts)} accounts, {num_posts} posts each")
    print(f"{'='*60}\n")

    results_all = []
    for i, account in enumerate(accounts):
        r = setup_account_profile(account, linktree_url, num_posts)
        results_all.append(r)

        if i < len(accounts) - 1:
            wait = random.uniform(30, 60)
            print(f"\nWaiting {wait:.0f}s before next account...")
            time.sleep(wait)

    ok_bios = sum(1 for r in results_all if r["bio"])
    total_posts = sum(r["posts"] for r in results_all)
    print(f"\n{'='*60}")
    print(f"PROFILE SETUP SUMMARY")
    print(f"Bios updated: {ok_bios}/{len(accounts)}")
    print(f"Posts uploaded: {total_posts}")
    print(f"{'='*60}")
