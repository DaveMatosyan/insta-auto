"""
Target scraper — find high-intent content buyers by scraping
commenters from competitor creator posts and scoring their profiles.

Usage:
    python target_scraper.py --creators handle1 handle2 --posts 9
    python target_scraper.py --creators handle1 --no-score --visible
"""

import argparse
import csv
import os
import random
import re
import time
from datetime import datetime

import gender_guesser.detector as gender_detector

from account_storage import get_all_accounts
from session_manager import open_session, close_session, ensure_logged_in
from config import (
    TARGET_CREATORS,
    SCRAPER_MAX_POSTS,
    SCRAPER_SCORE_PROFILES,
    SCRAPER_MIN_SCORE,
    SCRAPER_OUTPUT_CSV,
)

# --- Gender detector (singleton) ---
_gender_detector = gender_detector.Detector()

# --- Buyer-intent keyword / emoji lists ---
BUYER_EMOJIS = {'🔥', '❤️', '😍', '🤤', '👀', '💦', '😈', '💕', '😘', '💗',
                '🥵', '❤️‍🔥', '💯', '🫦', '😏', '💋', '🥰', '💓', '💖', '🫠'}

COMPLIMENT_KEYWORDS = [
    'beautiful', 'gorgeous', 'stunning', 'amazing', 'perfect',
    'incredible', 'sexy', 'hot', 'fine', 'wow', 'queen',
    'goddess', 'angel', 'body', 'omg', 'damn', 'fire',
    'babe', 'lovely', 'dream', 'breathtaking', 'flawless',
]

# Female bio keywords — used to filter OUT women
FEMALE_BIO_KEYWORDS = [
    'mom', 'mama', 'mother', 'she/her', 'girl boss', 'wifey',
    'wife', 'queen', 'goddess', 'woman', 'lady', 'sister',
    'daughter', 'feminine', 'her/', 'actress', 'model',
    'makeup artist', 'beauty', 'lash', 'nail tech',
]

# Business/creator bio keywords — deprioritize competitors
BUSINESS_BIO_KEYWORDS = [
    'creator', 'influencer', 'brand', 'agency', 'marketing',
    'photographer', 'booking', 'business', 'ceo', 'founder',
    'dm for collab', 'promo', 'manager', 'talent',
]


def human_delay(min_sec=1, max_sec=3):
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# 1. Scrape post links from a creator profile
# ---------------------------------------------------------------------------

def get_post_links(page, creator, max_posts=9):
    """
    Navigate to a creator's profile and collect post URLs.

    Returns:
        list of post URLs (e.g. /p/ABC123/)
    """
    print(f"\n📷 Scraping posts from @{creator}...")
    page.goto(f"https://www.instagram.com/{creator}/", wait_until="domcontentloaded", timeout=30000)
    human_delay(6, 9)

    # Debug: check what page loaded
    current_url = page.url
    title = page.title()
    print(f"   URL: {current_url}")
    print(f"   Title: {title}")

    # Scroll down multiple times to load more posts
    for scroll in range(4):
        page.mouse.wheel(0, 1200)
        human_delay(2, 3)

    # Extract post links via JS — try all possible href patterns
    links = page.evaluate(r"""() => {
        const hrefs = new Set();

        // Method 1: direct anchor links to /p/ or /reel/
        document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]').forEach(a => {
            const href = a.getAttribute('href');
            if (href) hrefs.add(href);
        });

        // Method 2: scan ALL anchors for post patterns
        if (hrefs.size === 0) {
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.getAttribute('href');
                if (href && (/\/p\/[A-Za-z0-9_-]+/.test(href) || /\/reel\/[A-Za-z0-9_-]+/.test(href))) {
                    hrefs.add(href);
                }
            });
        }

        // Debug: count all anchors on page
        const totalAnchors = document.querySelectorAll('a').length;
        console.log('Total anchors on page: ' + totalAnchors);

        return {links: [...hrefs], totalAnchors: totalAnchors};
    }""")

    total_anchors = links.get('totalAnchors', 0)
    links = links.get('links', [])[:max_posts]
    print(f"   Total anchors on page: {total_anchors}")
    print(f"   Found {len(links)} posts")
    return links


# ---------------------------------------------------------------------------
# 2. Scrape commenters from a single post
# ---------------------------------------------------------------------------

def scrape_post_commenters(page, post_path):
    """
    Navigate to a post and extract commenter usernames.

    Returns:
        list of dicts: [{"username": "...", "comment": "..."}, ...]
    """
    url = f"https://www.instagram.com{post_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    human_delay(3, 5)

    # Try to click "View all N comments" to expand
    try:
        view_all = page.locator('span:has-text("View all")').first
        if view_all.is_visible(timeout=5000):
            view_all.click()
            human_delay(3, 5)
    except:
        pass

    # Scroll the comment section to load more
    for _ in range(3):
        try:
            page.mouse.wheel(0, 600)
            human_delay(1, 2)
        except:
            break

    # Try clicking "+" / load more comments buttons
    for _ in range(3):
        try:
            more_btn = page.locator('button svg[aria-label="Load more comments"]').first
            if more_btn.is_visible(timeout=2000):
                more_btn.click()
                human_delay(2, 3)
        except:
            break

    # Extract commenter usernames and comment text
    commenters = page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        // Method 1: comment containers with username links
        document.querySelectorAll('ul li, div[role="button"]').forEach(el => {
            const link = el.querySelector('a[href^="/"]');
            const span = el.querySelector('span');
            if (link && span) {
                const href = link.getAttribute('href');
                const username = href.replace(/\\//g, '');
                if (username && !seen.has(username) && username.length > 1
                    && !username.includes('explore') && !username.includes('p/')) {
                    seen.add(username);
                    results.push({
                        username: username,
                        comment: span.textContent.substring(0, 200)
                    });
                }
            }
        });

        // Method 2: all user links on the comment page
        document.querySelectorAll('a[href^="/"]').forEach(a => {
            const href = a.getAttribute('href');
            const username = href.replace(/\\//g, '');
            if (username && !seen.has(username) && username.length > 2
                && !['explore', 'accounts', 'p', 'reels', 'stories', 'direct'].some(x => username.includes(x))) {
                seen.add(username);
                results.push({ username: username, comment: '' });
            }
        });

        return results;
    }""")

    # Filter out the creator themselves and common noise
    noise = {'instagram', 'explore', 'about', 'help', 'press', 'api', 'jobs', 'privacy', 'terms', 'locations', 'directory'}
    commenters = [c for c in commenters if c['username'].lower() not in noise and len(c['username']) > 2]

    print(f"   Post {post_path[:20]}... → {len(commenters)} commenters")
    return commenters


# ---------------------------------------------------------------------------
# 3. Scrape all commenters from a creator
# ---------------------------------------------------------------------------

def scrape_creator(page, creator, max_posts=9):
    """
    Scrape commenters from a creator's recent posts.

    Returns:
        dict: {username: {"comment": "...", "source_creator": "..."}, ...}
    """
    post_links = get_post_links(page, creator, max_posts)
    all_commenters = {}

    for i, link in enumerate(post_links):
        print(f"   Scraping post {i+1}/{len(post_links)}...")
        try:
            commenters = scrape_post_commenters(page, link)
            for c in commenters:
                uname = c['username']
                if uname not in all_commenters:
                    all_commenters[uname] = {
                        "comment": c['comment'],
                        "source_creator": creator,
                        "source_post": link,
                    }
        except Exception as e:
            print(f"   ❌ Error scraping {link}: {e}")

        # Wait between posts (longer for safety)
        if i < len(post_links) - 1:
            human_delay(8, 15)

    print(f"   ✅ @{creator}: {len(all_commenters)} unique commenters")
    return all_commenters


# ---------------------------------------------------------------------------
# 4. Score a profile for buyer potential
# ---------------------------------------------------------------------------

def detect_gender(fullname):
    """
    Detect gender from a display name using gender-guesser.

    Returns:
        str: 'male', 'female', 'mostly_male', 'mostly_female',
             'andy' (androgynous), or 'unknown'
    """
    if not fullname:
        return 'unknown'
    first_name = fullname.strip().split()[0].capitalize()
    return _gender_detector.get_gender(first_name)


def score_comment_intent(comment_text):
    """
    Score a comment for buyer intent based on emojis and keywords.

    Returns:
        (int, list): (score_points, list_of_reasons)
    """
    if not comment_text:
        return 0, []

    score = 0
    reasons = []
    text_lower = comment_text.lower()

    # Check buyer emojis
    emoji_hits = [e for e in BUYER_EMOJIS if e in comment_text]
    if emoji_hits:
        score += 2
        reasons.append(f"buyer_emojis({len(emoji_hits)})")

    # Check compliment keywords
    keyword_hits = [kw for kw in COMPLIMENT_KEYWORDS if kw in text_lower]
    if keyword_hits:
        score += 2
        reasons.append(f"compliments({','.join(keyword_hits[:3])})")

    return score, reasons


def is_female_profile(fullname, bio):
    """
    Check if a profile is likely female (to exclude).

    Returns:
        (bool, str): (is_female, reason)
    """
    # 1. Name-based detection
    gender = detect_gender(fullname)
    if gender in ('female', 'mostly_female'):
        return True, f"name_female({fullname})"

    # 2. Bio keyword detection
    if bio:
        bio_lower = bio.lower()
        for kw in FEMALE_BIO_KEYWORDS:
            if kw in bio_lower:
                return True, f"bio_female({kw})"

    return False, ""


def score_profile(page, username, comment_text=""):
    """
    Visit a profile and assign a buyer quality score (0-10).

    Scoring (max ~10 points):
        +1  following > followers (consumer, not creator)
        +1  followers < 5000 (not influencer)
        +1  following 500+ (follows many creators)
        +1  few posts (< 50) — lurker/consumer behavior
        +1  account is public
        +2  comment has buyer emojis (🔥❤️😍🤤👀)
        +2  comment has compliment keywords
        +1  no business/creator keywords in bio

    Gender filter:
        Returns None if detected as female (excluded)

    Returns:
        dict with score and profile data, or None on error/excluded
    """
    try:
        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=20000)
        human_delay(2, 3)

        profile = page.evaluate(r"""() => {
            // Get follower/following counts from meta or header
            const stats = [];
            document.querySelectorAll('header li, header ul li').forEach(li => {
                const text = li.textContent.replace(/,/g, '');
                const num = parseInt(text.replace(/[^0-9]/g, ''));
                if (!isNaN(num)) stats.push(num);
            });

            // Alternative: parse from meta description
            const meta = document.querySelector('meta[name="description"]');
            let metaFollowers = 0, metaFollowing = 0, metaPosts = 0;
            if (meta) {
                const content = meta.getAttribute('content') || '';
                const fm = content.match(/([\d,.]+[KkMm]?)\s*Follower/);
                const gm = content.match(/([\d,.]+[KkMm]?)\s*Following/);
                const pm = content.match(/([\d,.]+[KkMm]?)\s*Post/);
                if (fm) metaFollowers = fm[1];
                if (gm) metaFollowing = gm[1];
                if (pm) metaPosts = pm[1];
            }

            // Full display name
            const nameEl = document.querySelector('header section span') ||
                           document.querySelector('header h2');
            const fullname = nameEl ? nameEl.textContent.trim() : '';

            // Bio (grab all bio text, including link)
            const bioEl = document.querySelector('header section > div:not(:first-child) span');
            const bio = bioEl ? bioEl.textContent.trim() : '';

            // External link in bio (linktree, etc.)
            const linkEl = document.querySelector('header a[href*="l.instagram.com"]') ||
                           document.querySelector('header a[rel="me nofollow noopener noreferrer"]');
            const externalLink = linkEl ? linkEl.textContent.trim() : '';

            // Check if private
            const isPrivate = !!document.querySelector('h2:has-text("Private")') ||
                              document.body.textContent.includes('This account is private');

            // Check if verified (blue checkmark)
            const isVerified = !!document.querySelector('header svg[aria-label="Verified"]') ||
                               !!document.querySelector('header span[title="Verified"]');

            // Check if has active story ring (colored ring around profile pic)
            const hasStory = !!document.querySelector('header canvas') ||
                             !!document.querySelector('header div[role="button"] img[draggable]');

            // Profile picture URL (to check if default/custom)
            const pfpEl = document.querySelector('header img[alt*="profile picture"]') ||
                          document.querySelector('header img[data-testid="user-avatar"]');
            const pfpUrl = pfpEl ? pfpEl.getAttribute('src') : '';
            const hasCustomPfp = pfpUrl && !pfpUrl.includes('44884218_345707102882519');

            return {
                stats: stats,
                metaFollowers: metaFollowers,
                metaFollowing: metaFollowing,
                metaPosts: metaPosts,
                fullname: fullname.substring(0, 100),
                bio: bio.substring(0, 300),
                externalLink: externalLink.substring(0, 200),
                isPrivate: isPrivate,
                isVerified: isVerified,
                hasStory: hasStory,
                hasCustomPfp: hasCustomPfp,
            };
        }""")

        # Parse follower/following numbers
        def parse_num(val):
            if isinstance(val, (int, float)):
                return int(val)
            s = str(val).replace(',', '').strip()
            if not s:
                return 0
            if s[-1].lower() == 'k':
                return int(float(s[:-1]) * 1000)
            if s[-1].lower() == 'm':
                return int(float(s[:-1]) * 1000000)
            try:
                return int(s)
            except:
                return 0

        followers = parse_num(profile.get('metaFollowers', 0))
        following = parse_num(profile.get('metaFollowing', 0))
        posts = parse_num(profile.get('metaPosts', 0))
        fullname = profile.get('fullname', '')
        bio = profile.get('bio', '')
        external_link = profile.get('externalLink', '')
        is_private = profile.get('isPrivate', False)
        is_verified = profile.get('isVerified', False)
        has_story = profile.get('hasStory', False)
        has_custom_pfp = profile.get('hasCustomPfp', False)

        # Fallback to stats array if meta didn't work
        stats = profile.get('stats', [])
        if followers == 0 and len(stats) >= 2:
            posts = stats[0] if len(stats) >= 1 else 0
            followers = stats[1] if len(stats) >= 2 else 0
            following = stats[2] if len(stats) >= 3 else 0

        # --- GENDER FILTER: Exclude females ---
        female, female_reason = is_female_profile(fullname, bio)
        if female:
            print(f"      ♀️ Excluded @{username} — {female_reason}")
            return None

        # --- BUYER INTENT SCORING (max ~12) ---
        score = 0
        reasons = []

        # +1: following > followers (consumer behavior)
        if following > followers and followers > 0:
            score += 1
            reasons.append("consumer_ratio")

        # +1: small account (not influencer)
        if 0 < followers < 5000:
            score += 1
            reasons.append(f"small_acct({followers})")

        # +1: follows many accounts (500+)
        if following >= 500:
            score += 1
            reasons.append(f"follows_many({following})")

        # +1: few posts = lurker/consumer
        if 0 <= posts < 50:
            score += 1
            reasons.append(f"lurker({posts}_posts)")

        # +1: public account
        if not is_private:
            score += 1
            reasons.append("public")

        # +2: buyer emojis in comment
        # +2: compliment keywords in comment
        comment_score, comment_reasons = score_comment_intent(comment_text)
        score += comment_score
        reasons.extend(comment_reasons)

        # +1: no business/creator keywords in bio (not a competitor)
        bio_lower = bio.lower()
        has_business = any(kw in bio_lower for kw in BUSINESS_BIO_KEYWORDS)
        if not has_business:
            score += 1
            reasons.append("not_business")

        # +1: has custom profile pic (real person, not bot/empty)
        if has_custom_pfp:
            score += 1
            reasons.append("has_pfp")

        # -1: verified accounts are usually not buyers
        if is_verified:
            score -= 1
            reasons.append("verified_penalty")

        # Detect gender for reference (male/unknown kept)
        detected_gender = detect_gender(fullname)

        # Follow ratio for reference
        follow_ratio = round(following / max(followers, 1), 2)

        return {
            "username": username,
            "profile_url": f"https://www.instagram.com/{username}/",
            "followers": followers,
            "following": following,
            "follow_ratio": follow_ratio,
            "posts": posts,
            "fullname": fullname[:50],
            "bio": bio[:100],
            "external_link": external_link[:100],
            "is_private": is_private,
            "is_verified": is_verified,
            "has_story": has_story,
            "has_custom_pfp": has_custom_pfp,
            "gender": detected_gender,
            "score": score,
            "reasons": ",".join(reasons),
        }

    except Exception as e:
        print(f"      ⚠️ Could not score @{username}: {e}")
        return None


# ---------------------------------------------------------------------------
# 5. Save results to CSV
# ---------------------------------------------------------------------------

def save_targets_csv(targets, output_path):
    """Save scored targets to CSV"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    fieldnames = ["username", "profile_url", "score", "followers", "following",
                  "follow_ratio", "posts", "fullname", "bio", "external_link",
                  "is_private", "is_verified", "has_story", "has_custom_pfp",
                  "gender", "reasons", "source_creator", "source_post",
                  "comment", "scraped_at"]

    # Load existing to avoid duplicates
    existing = set()
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                existing.add(row.get('username', ''))

    new_count = 0
    with open(output_path, 'a' if existing else 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        if not existing:
            writer.writeheader()

        for t in targets:
            if t['username'] not in existing:
                writer.writerow(t)
                new_count += 1
                existing.add(t['username'])

    print(f"💾 Saved {new_count} new targets to {output_path} (total: {len(existing)})")
    return new_count


# ---------------------------------------------------------------------------
# 6. Also merge into the main tracker CSV for daily_follow
# ---------------------------------------------------------------------------

def merge_to_tracker(targets, tracker_path=None):
    """Add scored targets to the main username tracker for daily follows.
    Automatically skips duplicates."""
    if tracker_path is None:
        tracker_path = os.path.join(os.path.dirname(__file__),
                                     "csv_management", "csv_files", "usernames_tracker.csv")

    from csv_management.username_manager import UsernameTracker
    tracker = UsernameTracker(tracker_path)
    usernames = [t['username'] for t in targets]
    new_count = tracker.add_usernames_bulk(usernames)
    total = len(tracker.load_usernames())
    print(f"📋 Merged {new_count} new targets into tracker (total: {total})")


# ---------------------------------------------------------------------------
# 7. Main orchestrator
# ---------------------------------------------------------------------------

def run_scraper(creators=None, max_posts=None, score_profiles=None,
                min_score=None, headless=True, no_proxy=False):
    """
    Main scraper entry point.

    Args:
        creators: list of Instagram handles to scrape
        max_posts: posts per creator (default from config)
        score_profiles: whether to visit and score each profile
        min_score: minimum score to keep (0-10)
        headless: show browser or not
        no_proxy: force direct connection (ignore account proxy)

    Returns:
        list of target dicts
    """
    creators = creators or TARGET_CREATORS
    max_posts = max_posts or SCRAPER_MAX_POSTS
    if score_profiles is None:
        score_profiles = SCRAPER_SCORE_PROFILES
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    if not creators:
        print("❌ No creators to scrape! Add handles to TARGET_CREATORS in config.py")
        print("   Or use: python target_scraper.py --creators handle1 handle2")
        return []

    # Pick an account to use for scraping
    accounts = get_all_accounts()
    if not accounts:
        print("❌ No accounts available! Create one first with main.py")
        return []

    # Use the last (newest) account
    account = accounts[-1]

    # Strip proxy if --no-proxy flag is set (use own IP for scraping)
    if no_proxy:
        account = {**account, "proxy_url": None}
        print("🔓 No-proxy mode: using your own IP for scraping")

    print(f"\n{'='*60}")
    print(f"TARGET SCRAPER")
    print(f"Using account: @{account['username']}")
    print(f"Proxy: {'NONE (direct)' if no_proxy or not account.get('proxy_url') else account['proxy_url'][:40] + '...'}")
    print(f"Creators to scrape: {len(creators)} accounts")
    print(f"Posts per creator: {max_posts}")
    print(f"Score profiles: {score_profiles}")
    print(f"Min score: {min_score}")
    print(f"{'='*60}\n")

    # Open session
    session = open_session(account, headless=headless, block_images=False)
    if not ensure_logged_in(session):
        print("❌ Could not log in, aborting")
        close_session(session, save_cookies=False)
        return []

    page = session.page
    all_commenters = {}

    # --- Phase 1: Scrape commenters ---
    for creator in creators:
        try:
            commenters = scrape_creator(page, creator, max_posts)
            all_commenters.update(commenters)
        except Exception as e:
            print(f"❌ Error scraping @{creator}: {e}")

        # Wait between creators (longer to avoid bans)
        if creator != creators[-1]:
            wait = random.uniform(45, 90)
            print(f"⏳ Waiting {wait:.0f}s before next creator...")
            time.sleep(wait)

    print(f"\n{'='*60}")
    print(f"Phase 1 complete: {len(all_commenters)} unique commenters")
    print(f"{'='*60}\n")

    # --- Phase 2: Score profiles (optional) ---
    targets = []
    scored = 0
    skipped = 0

    if score_profiles and all_commenters:
        print(f"Scoring {len(all_commenters)} profiles...\n")
        usernames = list(all_commenters.keys())

        for i, username in enumerate(usernames):
            if i % 20 == 0 and i > 0:
                print(f"   Progress: {i}/{len(usernames)} scored...")

            comment_text = all_commenters[username].get('comment', '')
            profile_data = score_profile(page, username, comment_text=comment_text)
            if profile_data:
                scored += 1
                if profile_data['score'] >= min_score:
                    target = {
                        **profile_data,
                        "source_creator": all_commenters[username]['source_creator'],
                        "source_post": all_commenters[username]['source_post'],
                        "comment": comment_text[:100],
                        "scraped_at": datetime.now().isoformat(),
                    }
                    targets.append(target)
                else:
                    skipped += 1
            else:
                skipped += 1

            # Rate limit: wait between profile visits (longer for safety)
            if i < len(usernames) - 1:
                human_delay(4, 8)

            # Every 25 profiles, take a longer break
            if i > 0 and i % 25 == 0:
                wait = random.uniform(30, 60)
                print(f"   ⏳ Rate limit break ({wait:.0f}s)...")
                time.sleep(wait)

            # Every 100 profiles, take an even longer break
            if i > 0 and i % 100 == 0:
                wait = random.uniform(120, 180)
                print(f"   🛑 Long cooldown ({wait:.0f}s) to avoid ban...")
                time.sleep(wait)
    else:
        # No scoring — keep all commenters with default score
        for username, data in all_commenters.items():
            targets.append({
                "username": username,
                "profile_url": f"https://www.instagram.com/{username}/",
                "score": 0,
                "followers": 0,
                "following": 0,
                "follow_ratio": 0,
                "posts": 0,
                "fullname": "",
                "bio": "",
                "external_link": "",
                "is_private": False,
                "is_verified": False,
                "has_story": False,
                "has_custom_pfp": False,
                "gender": "unknown",
                "reasons": "not_scored",
                "source_creator": data['source_creator'],
                "source_post": data['source_post'],
                "comment": data.get('comment', '')[:100],
                "scraped_at": datetime.now().isoformat(),
            })

    close_session(session, save_cookies=True)

    # --- Phase 3: Save results ---
    print(f"\n{'='*60}")
    print(f"SCRAPER RESULTS")
    print(f"Total commenters found: {len(all_commenters)}")
    print(f"Profiles scored: {scored}")
    print(f"Qualified targets (score >= {min_score}): {len(targets)}")
    print(f"Filtered out: {skipped}")
    print(f"{'='*60}\n")

    if targets:
        save_targets_csv(targets, SCRAPER_OUTPUT_CSV)
        merge_to_tracker(targets)

    return targets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape high-intent targets from competitor creators")
    parser.add_argument("--creators", nargs="+", help="Creator handles to scrape (e.g. handle1 handle2)")
    parser.add_argument("--posts", type=int, default=None, help="Posts to scrape per creator (default: 12)")
    parser.add_argument("--no-score", action="store_true", help="Skip profile scoring (faster, less accurate)")
    parser.add_argument("--min-score", type=int, default=None, help="Minimum quality score 0-10 (default: 4)")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--no-proxy", action="store_true", help="Use direct connection (no proxy)")
    args = parser.parse_args()

    run_scraper(
        creators=args.creators,
        max_posts=args.posts,
        score_profiles=not args.no_score,
        min_score=args.min_score,
        headless=not args.visible,
        no_proxy=args.no_proxy,
    )


if __name__ == "__main__":
    main()
