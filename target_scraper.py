"""
Target scraper — find high-intent content buyers by scraping
commenters from competitor creator posts and scoring their profiles.

Scoring: Gemini 2.5 Flash AI analyzes each profile for gender + buyer intent.

Usage:
    python target_scraper.py --creators handle1 handle2 --posts 9
    python target_scraper.py --creators handle1 --no-score --visible
"""

import argparse
import csv
import json
import os
import random
import re
import time
from datetime import datetime

import google.generativeai as genai

from account_storage import get_all_accounts
from session_manager import open_session, close_session, ensure_logged_in
from config import (
    TARGET_CREATORS,
    SCRAPER_MAX_POSTS,
    SCRAPER_SCORE_PROFILES,
    SCRAPER_MIN_SCORE,
    SCRAPER_OUTPUT_CSV,
)

# --- Gemini AI config ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
AI_BATCH_SIZE = 15  # profiles per API call


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
# 4. Extract raw profile data (no scoring — just data collection)
# ---------------------------------------------------------------------------

def get_profile_data(page, username):
    """
    Visit a profile and extract raw data for AI scoring.

    Returns:
        dict with profile data, or None on error
    """
    try:
        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=20000)
        human_delay(2, 3)

        profile = page.evaluate(r"""() => {
            // --- STATS: parse from meta description (most reliable) ---
            const meta = document.querySelector('meta[name="description"]');
            let metaFollowers = 0, metaFollowing = 0, metaPosts = 0, metaName = '';
            if (meta) {
                const content = meta.getAttribute('content') || '';
                const fm = content.match(/([\d,.]+[KkMm]?)\s*Follower/);
                const gm = content.match(/([\d,.]+[KkMm]?)\s*Following/);
                const pm = content.match(/([\d,.]+[KkMm]?)\s*Post/);
                if (fm) metaFollowers = fm[1];
                if (gm) metaFollowing = gm[1];
                if (pm) metaPosts = pm[1];
                // Meta often has: "... from Display Name (@handle)"
                const nm = content.match(/from\s+(.+?)\s*\(@/);
                if (nm) metaName = nm[1].trim();
            }

            // --- STATS: fallback from header stats ---
            const stats = [];
            document.querySelectorAll('header li, header ul li').forEach(li => {
                const text = li.textContent.replace(/,/g, '');
                const num = parseInt(text.replace(/[^0-9]/g, ''));
                if (!isNaN(num)) stats.push(num);
            });

            // --- FULL NAME: try multiple strategies ---
            let fullname = '';

            // Strategy 1: <title> tag often has "Display Name (@handle)"
            const titleMatch = document.title.match(/^(.+?)\s*\(@/);
            if (titleMatch) fullname = titleMatch[1].trim();

            // Strategy 2: meta description name
            if (!fullname && metaName) fullname = metaName;

            // Strategy 3: header span that looks like a name (not stats, not username)
            if (!fullname) {
                const headerSpans = document.querySelectorAll('header section span');
                for (const sp of headerSpans) {
                    const t = sp.textContent.trim();
                    if (t && t.length > 1 && t.length < 60
                        && !/^\d/.test(t) && !t.includes('follower') && !t.includes('following')
                        && !t.includes('post') && !t.includes('@') && !t.includes('http')
                        && !t.includes('Edit') && !t.includes('Follow')
                        && !/^\d+$/.test(t.replace(/[,.\s]/g, ''))) {
                        fullname = t;
                        break;
                    }
                }
            }

            // --- BIO: try multiple strategies ---
            let bio = '';

            // Strategy 1: meta description often has bio after " - "
            if (meta) {
                const content = meta.getAttribute('content') || '';
                const bioParts = content.split(' - ');
                if (bioParts.length > 1) {
                    const lastPart = bioParts[bioParts.length - 1].trim();
                    if (!lastPart.startsWith('See Instagram')) {
                        bio = lastPart.replace(/^[""]|[""]$/g, '').trim();
                    }
                }
            }

            // Strategy 2: look for bio in header section
            if (!bio) {
                const allSpans = document.querySelectorAll('header span');
                for (const sp of allSpans) {
                    const t = sp.textContent.trim();
                    if (t && t.length > 10 && t.length < 300
                        && !/^\d/.test(t) && !t.includes('follower') && !t.includes('following')
                        && t !== fullname && !t.includes('Threads')
                        && !t.includes('Edit profile') && !t.includes('Follow')) {
                        bio = t;
                        break;
                    }
                }
            }

            // --- EXTERNAL LINK ---
            const linkEl = document.querySelector('a[href*="l.instagram.com"]') ||
                           document.querySelector('a[rel="me nofollow noopener noreferrer"]') ||
                           document.querySelector('header a[href^="http"]');
            const externalLink = linkEl ? linkEl.textContent.trim() : '';

            // --- PRIVATE CHECK ---
            const bodyText = document.body.textContent;
            const isPrivate = bodyText.includes('This account is private') ||
                              bodyText.includes('This Account is Private');

            // --- VERIFIED ---
            const isVerified = !!document.querySelector('svg[aria-label="Verified"]') ||
                               !!document.querySelector('span[title="Verified"]');

            // --- STORY ---
            const hasStory = !!document.querySelector('header canvas') ||
                             !!document.querySelector('header div[role="button"] img[draggable]');

            // --- PROFILE PIC ---
            const pfpEl = document.querySelector('img[alt*="profile picture"]') ||
                          document.querySelector('img[data-testid="user-avatar"]') ||
                          document.querySelector('header img');
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

        follow_ratio = round(following / max(followers, 1), 2)

        return {
            "username": username,
            "profile_url": f"https://www.instagram.com/{username}/",
            "followers": followers,
            "following": following,
            "follow_ratio": follow_ratio,
            "posts": posts,
            "fullname": fullname[:50],
            "bio": bio[:150],
            "external_link": external_link[:100],
            "is_private": is_private,
            "is_verified": is_verified,
            "has_story": has_story,
            "has_custom_pfp": has_custom_pfp,
        }

    except Exception as e:
        print(f"      ⚠️ Could not get data for @{username}: {e}")
        return None


# ---------------------------------------------------------------------------
# 5. Gemini AI scoring — batch profiles for gender + buyer intent
# ---------------------------------------------------------------------------

def _init_gemini():
    """Initialize Gemini client."""
    api_key = GEMINI_API_KEY
    if not api_key:
        # Try loading from config file
        key_file = os.path.join(os.path.dirname(__file__), "gemini_api_key.txt")
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                api_key = f.read().strip()
    if not api_key:
        raise ValueError(
            "No Gemini API key found! Set GEMINI_API_KEY env var or create gemini_api_key.txt"
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def ai_score_batch(model, profiles_batch, comments_map):
    """
    Send a batch of profiles to Gemini for AI scoring.

    Args:
        model: Gemini GenerativeModel instance
        profiles_batch: list of profile dicts (raw data from get_profile_data)
        comments_map: dict {username: comment_text}

    Returns:
        list of dicts with AI scores: [{"username": "...", "gender": "...", "score": N, "reasons": "..."}, ...]
    """
    # Build the profile summaries for the prompt
    profile_lines = []
    for p in profiles_batch:
        username = p['username']
        comment = comments_map.get(username, '')
        line = (
            f"- @{username} | name: {p.get('fullname', 'N/A')} | "
            f"bio: {p.get('bio', 'N/A')} | "
            f"followers: {p.get('followers', 0)} | following: {p.get('following', 0)} | "
            f"posts: {p.get('posts', 0)} | "
            f"private: {p.get('is_private', False)} | verified: {p.get('is_verified', False)} | "
            f"has_pfp: {p.get('has_custom_pfp', False)} | "
            f"link: {p.get('external_link', '')} | "
            f"comment: {comment[:120]}"
        )
        profile_lines.append(line)

    profiles_text = "\n".join(profile_lines)

    prompt = f"""You are a senior digital marketing analyst specializing in adult content creator monetization (OnlyFans, Fansly). You have 10+ years of experience identifying high-value male subscribers by analyzing their social media behavior. Your conversion predictions are used by top agencies to build targeted follower funnels.

YOUR TASK: You are given a batch of Instagram profiles. These were scraped from the comment sections of popular female fitness models and bikini competitors. Your job is to determine for each profile:

1. Is this a POTENTIAL BUYER — a male who would subscribe and pay for exclusive female content?
2. Give each profile a score from 0 to 10 representing how likely they are to become a paying subscriber.

HOW YOU WORK — Your analysis process for each profile:

Step 1 — GENDER CLASSIFICATION:
You look at username, display name, and bio TOGETHER to determine gender. You know from experience:
- Usernames containing female names (jessica, sarah, maria, bella, nayla, bruna, claudia, sonya, michelle, julia, grace, maddy, dawn, kaela, rhia, nita, mae, yaneth) → female
- Usernames with "girl", "queen", "mama", "babe", "princess", "goddess", "gurl", "diva", "lady", "bella", "chica", "miss" → female
- Bio with "mom", "wife", "she/her", "actress", "model", "lash", "nail tech", "beauty", "feminine" → female
- Bio with IFBB, NPC, bikini pro, fitness competitor, athlete, coach → usually female competitor (they comment on each other's posts, they are NOT buyers)
- Usernames with male names (john, mike, james, ahmed, carlos, pedro, hermes, shariq, parth, steel) → male
- Accounts that are clearly brands, shops, meal prep, supplement companies → business, not a buyer
- When gender is truly unclear → "unknown"

Step 2 — BUYER INTENT SCORING (0-10):
You analyze behavioral signals that predict whether someone will pay for content:

CRITICAL CONTEXT: These profiles were scraped from comments on FEMALE fitness/bikini model posts. Statistically 70-80% of commenters on these posts are male. So if gender is unclear but the account shows consumer behavior, assume likely male and score accordingly (don't give 0 to unknowns — give them 3-5 based on their signals).

STRONG BUYER SIGNALS (each adds points):
• Male gender confirmed → base score starts at 5
• Gender unknown but consumer behavior → base score starts at 3
• following > followers ratio (they consume, don't create) → +1-2
• Follows 500+ accounts (follows many creators) → +1
• Less than 50 posts (lurker/viewer, not a poster) → +1
• Small account under 5000 followers (regular person, not influencer) → +1
• Comment contains thirsty emojis: 🔥❤️😍🤤👀💦😈🥵💋😏 → +1-2
• Comment contains compliment words: beautiful, gorgeous, stunning, hot, sexy, amazing, perfect, incredible, queen, goddess, damn, wow, fire, fine → +1-2
• Has a profile picture (real person, engaged user) → +1
• Private account with consumer ratio → still a buyer signal (they hide their activity)

DISQUALIFYING SIGNALS (score 0-1):
• Confirmed female — they don't buy female content → score 0
• Business/brand account — no individual buyer → score 1
• IFBB pro, fitness competitor, bikini athlete — they are peers, not customers → score 0
• Verified celebrity — not a buyer → score 1
• Bot-like account (0 followers, 0 following, no pfp) → score 0
• Very high follower count 50k+ (they're creators themselves) → score 2

PROFILES TO ANALYZE:
{profiles_text}

RESPOND WITH ONLY A RAW JSON ARRAY. No explanation, no markdown formatting, no ```json code blocks.
Each object must have exactly these 4 fields: username, gender, score, reasons.
The "reasons" field MUST list specific signals you found (e.g. "male name, consumer ratio 8.0, follows 2190, lurker 0 posts, thirsty emoji 🔥"). Never write just "Female." or "Gender unknown." — always explain WHY.

Example:
[{{"username":"john_doe123","gender":"male","score":8,"reasons":"male name John, following(2100)>followers(450), lurker 3 posts, thirsty comment with 🔥, has pfp"}},{{"username":"jessica.fit","gender":"female","score":0,"reasons":"female name Jessica, IFBB in bio, fitness competitor peer"}}]"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Clean up response — remove markdown code blocks if present
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        text = text.strip()

        results = json.loads(text)

        # Validate structure
        if not isinstance(results, list):
            print(f"      ⚠️ AI returned non-list response, skipping batch")
            return []

        return results

    except json.JSONDecodeError as e:
        print(f"      ⚠️ AI response was not valid JSON: {e}")
        print(f"      Raw response: {text[:300]}")
        return []
    except Exception as e:
        print(f"      ⚠️ AI scoring failed: {e}")
        return []


# ---------------------------------------------------------------------------
# 6. Save results to CSV
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
# 7. Also merge into the main tracker CSV for daily_follow
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
# 8. Main orchestrator
# ---------------------------------------------------------------------------

def run_scraper(creators=None, max_posts=None, score_profiles=None,
                min_score=None, headless=True, no_proxy=False):
    """
    Main scraper entry point.

    Flow:
        Phase 1: Scrape commenters from creator posts
        Phase 2: Visit each commenter's profile → collect raw data
        Phase 3: Send batches to Gemini AI for gender/buyer scoring
        Phase 4: Save qualified targets to CSV

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

    if no_proxy:
        print("🔓 No-proxy mode: using your own IP for scraping")

    # Init Gemini if scoring is enabled
    gemini_model = None
    if score_profiles:
        try:
            gemini_model = _init_gemini()
            print(f"🤖 Gemini AI scoring enabled ({GEMINI_MODEL})")
        except Exception as e:
            print(f"❌ Could not initialize Gemini: {e}")
            print("   Set GEMINI_API_KEY env var or create gemini_api_key.txt")
            return []

    print(f"\n{'='*60}")
    print(f"TARGET SCRAPER")
    print(f"Using account: @{account['username']}")
    print(f"Proxy: {'NONE (direct)' if no_proxy else 'auto-rotating (ProxyShare)'}")
    print(f"Creators to scrape: {len(creators)} accounts")
    print(f"Posts per creator: {max_posts}")
    print(f"Score profiles: {score_profiles} (Gemini AI)")
    print(f"Min score: {min_score}")
    print(f"{'='*60}\n")

    # Open session (proxy auto-rotates via proxy_manager)
    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
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

    # --- Phase 2: Collect profile data ---
    all_profiles = []
    comments_map = {}  # username → comment text

    if score_profiles and all_commenters:
        print(f"📊 Collecting profile data for {len(all_commenters)} users...\n")
        usernames = list(all_commenters.keys())

        for i, username in enumerate(usernames):
            if i % 20 == 0 and i > 0:
                print(f"   Progress: {i}/{len(usernames)} profiles collected...")

            profile_data = get_profile_data(page, username)
            if profile_data:
                all_profiles.append(profile_data)
                comment_text = all_commenters[username].get('comment', '')
                comments_map[username] = comment_text

            # Rate limit: wait between profile visits
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

        print(f"\n   ✅ Collected data for {len(all_profiles)} profiles")

    close_session(session, save_cookies=True)

    # --- Phase 3: AI scoring with Gemini ---
    targets = []

    if score_profiles and all_profiles and gemini_model:
        print(f"\n{'='*60}")
        print(f"Phase 3: AI scoring {len(all_profiles)} profiles with Gemini...")
        print(f"{'='*60}\n")

        # Process in batches
        for batch_start in range(0, len(all_profiles), AI_BATCH_SIZE):
            batch = all_profiles[batch_start:batch_start + AI_BATCH_SIZE]
            batch_end = min(batch_start + AI_BATCH_SIZE, len(all_profiles))
            print(f"   🤖 Scoring batch {batch_start+1}-{batch_end} / {len(all_profiles)}...")

            ai_results = ai_score_batch(gemini_model, batch, comments_map)

            # Match AI results back to profile data
            ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

            for profile in batch:
                username = profile['username']
                ai = ai_map.get(username, {})

                gender = ai.get('gender', 'unknown')
                score = ai.get('score', 0)
                reasons = ai.get('reasons', 'ai_no_response')

                # Filter: exclude females and low scores
                if gender == 'female':
                    print(f"      ♀️ Excluded @{username} — AI: female ({reasons})")
                    continue

                if score < min_score:
                    continue

                target = {
                    **profile,
                    "gender": gender,
                    "score": score,
                    "reasons": reasons[:150],
                    "source_creator": all_commenters.get(username, {}).get('source_creator', ''),
                    "source_post": all_commenters.get(username, {}).get('source_post', ''),
                    "comment": comments_map.get(username, '')[:100],
                    "scraped_at": datetime.now().isoformat(),
                }
                targets.append(target)

            # Small delay between API calls to avoid rate limiting
            if batch_end < len(all_profiles):
                time.sleep(2)

    elif not score_profiles:
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

    # --- Phase 4: Save results ---
    total_scored = len(all_profiles) if score_profiles else 0
    print(f"\n{'='*60}")
    print(f"SCRAPER RESULTS")
    print(f"Total commenters found: {len(all_commenters)}")
    print(f"Profiles collected: {total_scored}")
    print(f"AI-qualified targets (score >= {min_score}): {len(targets)}")
    print(f"Filtered out: {total_scored - len(targets)}")
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
