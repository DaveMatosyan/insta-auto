"""
Profile setup — upload posts, set bio, add linktree link.
Uses shared core/api_client.py for instagrapi sessions.
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
from core.api_client import create_api_client, save_api_session

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


def update_bio(cl, bio_text, linktree_url=None):
    """Update Instagram bio and website link via API."""
    try:
        cl.account_edit(biography=bio_text, external_url=linktree_url or "")
        print(f"  [profile] Bio updated: {bio_text[:50]}...")
        if linktree_url:
            print(f"  [profile] Website: {linktree_url}")
        return True
    except Exception as e:
        print(f"  [profile] Error updating bio: {e}")
        return False


def upload_post(cl, image_path, caption=""):
    """Upload a photo post via API."""
    try:
        media = cl.photo_upload(image_path, caption=caption)
        print(f"  [profile] Posted: {os.path.basename(image_path)} (id={media.pk})")
        return True
    except Exception as e:
        print(f"  [profile] Error uploading {os.path.basename(image_path)}: {e}")
        return False


def setup_account_profile(account, linktree_url=None, num_posts=6, **kwargs):
    """
    Full profile setup for one account via API.
    """
    username = account.get("username", "???")
    print(f"\n{'='*40}")
    print(f"Setting up profile for @{username}")
    print(f"{'='*40}")

    images = get_profile_images()
    if not images and num_posts > 0:
        print("[profile] No images in data/profile_images/ -- add photos and re-run")

    cl = create_api_client(account)
    if not cl:
        print(f"  [profile] Could not log in @{username} -- skipping")
        return {"bio": False, "posts": 0}

    results = {"bio": False, "posts": 0}

    # 1. Update bio
    bio = random.choice(BIO_TEMPLATES)
    results["bio"] = update_bio(cl, bio, linktree_url)

    # 2. Upload posts
    if images and num_posts > 0:
        selected = random.sample(images, min(num_posts, len(images)))
        for img in selected:
            caption = random.choice(POST_CAPTIONS)
            if upload_post(cl, img, caption):
                results["posts"] += 1
            time.sleep(random.uniform(15, 30))
    else:
        print("  [profile] Skipping posts (0 images)")

    save_api_session(cl, username)

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
