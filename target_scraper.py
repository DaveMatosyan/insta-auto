"""
Target scraper — find high-intent content buyers by scraping
commenters from competitor creator posts and scoring their profiles.

Scoring: Gemini 2.5 Flash AI analyzes each profile for gender + buyer intent.

3-step workflow:
    Step 1: Scrape raw usernames
        python target_scraper.py --scrape-only --count 50 --no-proxy
    Step 2: Manually edit raw_commenters.txt — remove obvious non-buyers
    Step 3: Score remaining with Gemini
        python target_scraper.py --score-file raw_commenters.txt --no-proxy

Legacy (all-in-one):
    python target_scraper.py --creators handle1 handle2 --posts 9
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
GEMINI_MODEL = "gemini-2.5-flash"  # 2.0-flash deprecated for new projects; 2.5-flash works on fresh keys
AI_BATCH_SIZE = 20  # profiles per API call

# --- Hover interception noise (usernames to skip hovering) ---
_HOVER_NOISE = {
    'instagram', 'explore', 'accounts', 'reels', 'stories',
    'direct', 'p', 'about', 'help', 'press', 'api', 'jobs',
    'privacy', 'terms', 'locations', 'directory',
}


def human_delay(min_sec=1, max_sec=3):
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Hover API interception — parse Instagram's profile info endpoint response
# ---------------------------------------------------------------------------

def _parse_api_user(user: dict) -> dict:
    """
    Parse an Instagram API user object (from /api/v1/users/web_profile_info/)
    into our standard profile dict format.

    This is the same data we'd get from visiting a profile page, but
    obtained by intercepting the API call triggered on username hover —
    zero extra page navigation needed.
    """
    followers = int(user.get('edge_followed_by', {}).get('count', 0) or 0)
    following = int(user.get('edge_follow', {}).get('count', 0) or 0)
    posts = int(user.get('edge_owner_to_timeline_media', {}).get('count', 0) or 0)
    pfp = user.get('profile_pic_url_hd') or user.get('profile_pic_url') or ''
    bio_links = user.get('bio_links') or []
    ext_link = user.get('external_url') or ''
    if not ext_link and bio_links:
        ext_link = bio_links[0].get('url') or bio_links[0].get('title') or ''
    username = user.get('username', '')
    return {
        'username': username,
        'profile_url': f'https://www.instagram.com/{username}/',
        'followers': followers,
        'following': following,
        'follow_ratio': round(following / max(followers, 1), 2),
        'posts': posts,
        'fullname': (user.get('full_name') or '')[:50],
        'bio': (user.get('biography') or '')[:150],
        'external_link': ext_link[:100],
        'is_private': bool(user.get('is_private', False)),
        'is_verified': bool(user.get('is_verified', False)),
        'has_story': False,   # not exposed by this endpoint
        'has_custom_pfp': bool(pfp and '44884218' not in pfp),
    }


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

    # Debug: check page content for login walls / errors
    page_debug = page.evaluate("""() => {
        const text = document.body.innerText.substring(0, 500);
        const allHrefs = Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href')).slice(0, 30);
        return {bodyPreview: text, hrefs: allHrefs};
    }""")
    print(f"   Body preview: {page_debug.get('bodyPreview', '')[:200]}")
    print(f"   First hrefs: {page_debug.get('hrefs', [])[:10]}")

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

    # --- Hover over visible comment author links to trigger profile API calls ---
    # Instagram fires GET /api/v1/users/web_profile_info/?username=X on hover.
    # A response listener (set up in run_scrape_only) intercepts those responses
    # and stores full profile data — so no extra page navigation is needed later.
    try:
        target_usernames = {c['username'] for c in commenters}
        links = page.locator('ul li a[href^="/"], article a[href^="/"]').all()
        hovered = 0
        for link in links:
            try:
                href = (link.get_attribute('href', timeout=500) or '').strip('/')
                if (href and href not in _HOVER_NOISE and '/' not in href
                        and href in target_usernames):
                    link.scroll_into_view_if_needed()
                    link.hover(timeout=2000)
                    time.sleep(0.35)    # short wait for API call to fire
                    hovered += 1
                    if hovered >= 30:   # cap per post to avoid being too mechanical
                        break
            except Exception:
                continue
        if hovered:
            page.mouse.move(10, 10)     # move away so last popup closes
            time.sleep(0.3)
            print(f"   ↩️  Hovered {hovered} links (profile data collected via API)")
    except Exception:
        pass

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
# 5. Mechanical pre-filter — cut obvious non-buyers before Gemini
# ---------------------------------------------------------------------------

FEMALE_NAMES = {
    'jessica', 'sarah', 'maria', 'bella', 'nayla', 'bruna', 'claudia', 'sonya',
    'michelle', 'julia', 'grace', 'maddy', 'dawn', 'kaela', 'rhia', 'nita',
    'mae', 'yaneth', 'anna', 'emma', 'olivia', 'sophia', 'ava', 'mia',
    'isabella', 'emily', 'abigail', 'ella', 'chloe', 'lily', 'hannah', 'natalie',
    'samantha', 'victoria', 'madison', 'elizabeth', 'avery', 'scarlett', 'aria',
    'penelope', 'layla', 'riley', 'zoey', 'nora', 'camila', 'elena', 'luna',
    'savannah', 'aubrey', 'brooklyn', 'leah', 'zoe', 'stella', 'hazel', 'ellie',
    'paisley', 'audrey', 'skylar', 'violet', 'claire', 'bella', 'lucy', 'aaliyah',
    'caroline', 'genesis', 'emilia', 'kennedy', 'maya', 'willow', 'kinsley',
    'naomi', 'ariana', 'ruby', 'eva', 'serenity', 'autumn', 'adeline', 'hailey',
    'gianna', 'valentina', 'isla', 'eliana', 'quinn', 'nevaeh', 'ivy', 'sadie',
    'piper', 'lydia', 'alexa', 'josie', 'andrea', 'gabriella', 'alejandra',
    'daniela', 'fernanda', 'paola', 'valeria', 'mariana', 'catalina', 'tatiana',
    'priya', 'aisha', 'fatima', 'yasmin', 'lina', 'nina', 'tara', 'diana',
    'laura', 'paula', 'sandra', 'monica', 'carmen', 'rosa', 'angela', 'lisa',
    'jennifer', 'amanda', 'stephanie', 'heather', 'ashley', 'brittany', 'kelsey',
    'megan', 'rachel', 'rebecca', 'katherine', 'amber', 'nicole', 'tiffany',
    'crystal', 'vanessa', 'bianca', 'jasmine', 'alicia', 'veronica', 'kathleen',
}

FEMALE_KEYWORDS = {
    'girl', 'queen', 'mama', 'babe', 'princess', 'goddess', 'gurl', 'diva',
    'lady', 'chica', 'miss', 'missy', 'wifey', 'sissy', 'barbie', 'dolly',
}

BRAND_KEYWORDS = {
    'shop', 'store', 'brand', 'official', 'media', 'agency', 'studio',
    'photography', 'magazine', 'daily', 'news', 'memes', 'repost', 'fanpage',
    'clothing', 'apparel', 'boutique', 'fitness_brand', 'supplements',
    'coaching', 'nutrition', 'mealprep', 'podcast', 'radio',
}

COMPETITOR_BIO_KEYWORDS = {
    'ifbb', 'npc', 'bikini pro', 'figure pro', 'wellness pro',
    'fitness competitor', 'bodybuilding', 'physique', 'wbff',
    'olympia', 'arnold classic', 'prep coach',
}


def pre_filter_profile(profile, comment=''):
    """
    Mechanical pre-filter. Returns (keep, reason) tuple.
    keep=True means send to Gemini, keep=False means skip.
    """
    username = profile.get('username', '').lower()
    fullname = profile.get('fullname', '').lower()
    bio = profile.get('bio', '').lower()
    followers = profile.get('followers', 0)
    following = profile.get('following', 0)
    posts = profile.get('posts', 0)
    has_pfp = profile.get('has_custom_pfp', False)

    # --- BOT: no followers, no following, no pfp ---
    if followers == 0 and following == 0 and not has_pfp:
        return False, "bot (0/0/no pfp)"

    # --- BIG CREATOR: 50k+ followers = they're a creator, not buyer ---
    if followers >= 50000:
        return False, f"big creator ({followers} followers)"

    # --- FEMALE NAME in username ---
    username_clean = re.sub(r'[_.\d]+', ' ', username).strip()
    for name in FEMALE_NAMES:
        if name in username_clean.split() or username_clean.startswith(name):
            return False, f"female name '{name}' in username"

    # --- FEMALE NAME in fullname ---
    fullname_words = fullname.split()
    for name in FEMALE_NAMES:
        if name in fullname_words:
            return False, f"female name '{name}' in fullname"

    # --- FEMALE KEYWORDS in username ---
    for kw in FEMALE_KEYWORDS:
        if kw in username:
            return False, f"female keyword '{kw}' in username"

    # --- BRAND/BUSINESS ---
    for kw in BRAND_KEYWORDS:
        if kw in username:
            return False, f"brand keyword '{kw}' in username"

    # --- FITNESS COMPETITOR in bio ---
    for kw in COMPETITOR_BIO_KEYWORDS:
        if kw in bio:
            return False, f"competitor keyword '{kw}' in bio"

    # --- FEMALE BIO signals ---
    female_bio_signals = ['she/her', 'mom of', 'mother of', 'wife of', 'wifey',
                          'nail tech', 'lash tech', 'esthetician', 'makeup artist',
                          'model ', 'actress', 'dancer', 'onlyfans.com']
    for sig in female_bio_signals:
        if sig in bio:
            return False, f"female bio signal '{sig}'"

    return True, "passed"


# ---------------------------------------------------------------------------
# 6. Gemini AI scoring — batch profiles for gender + buyer intent
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

    max_retries = 5
    for attempt in range(max_retries):
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
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                wait = min(30 * (2 ** attempt), 300)  # 30s, 60s, 120s, 240s, 300s
                print(f"      ⏳ Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"      ⚠️ AI scoring failed: {e}")
            return []

    print(f"      ⚠️ AI scoring failed after {max_retries} retries (quota exhausted)")
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
# 8a. Scrape-only mode — just collect usernames, save to file
# ---------------------------------------------------------------------------

RAW_COMMENTERS_TXT = os.path.join(os.path.dirname(__file__), "raw_commenters.txt")
RAW_COMMENTERS_JSON = os.path.join(os.path.dirname(__file__), "raw_commenters.json")


def run_scrape_only(creators=None, max_posts=None, count=50,
                    headless=True, no_proxy=False, min_score=None):
    """
    Full pipeline with crash-safe incremental saves:
        1. Scrape ~count usernames from creator comments → save to disk
        2. Process in batches of AI_BATCH_SIZE:
           visit profiles → pre-filter → Gemini score → save to CSV
        3. Resume-safe: skips already-processed usernames on restart

    Args:
        count: how many raw usernames to scrape before processing
    """
    creators = creators or TARGET_CREATORS
    max_posts = max_posts or SCRAPER_MAX_POSTS
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    accounts = get_all_accounts()
    if not accounts:
        print("❌ No accounts available!")
        return

    # Pick account with valid cookies
    account = None
    for acc in reversed(accounts):
        cookie_file = os.path.join("sessions", f"{acc['username']}_state.json")
        if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 5000:
            account = acc
            print(f"🔑 Using account @{acc['username']} (has valid cookies)")
            break
    if account is None:
        account = accounts[-1]
        print(f"⚠️ No account with valid cookies, trying @{account['username']}")

    # Init Gemini
    try:
        gemini_model = _init_gemini()
        print(f"🤖 Gemini AI ready ({GEMINI_MODEL})")
    except Exception as e:
        print(f"❌ Could not initialize Gemini: {e}")
        return

    # Load already-processed usernames (from CSV + a "visited" checkpoint file)
    already_processed = set()
    if os.path.exists(SCRAPER_OUTPUT_CSV):
        with open(SCRAPER_OUTPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                already_processed.add(row.get('username', ''))

    # Checkpoint file: tracks ALL visited usernames (including filtered/low-score ones)
    checkpoint_file = os.path.join(os.path.dirname(__file__), "scrape_checkpoint.json")
    checkpoint = {"visited": [], "scraped_commenters": {}}
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
            print(f"📋 Loaded checkpoint: {len(checkpoint.get('visited', []))} previously visited")
        except:
            pass
    visited_set = set(checkpoint.get("visited", []))
    # Merge CSV usernames into visited set too
    visited_set.update(already_processed)

    print(f"\n{'='*60}")
    print(f"SCRAPE → FILTER → SCORE PIPELINE")
    print(f"Account: @{account['username']}")
    print(f"Proxy: {'NONE (direct)' if no_proxy else 'auto-rotating'}")
    print(f"Creators: {len(creators)} | Posts/creator: {max_posts}")
    print(f"Target count: {count} raw usernames")
    print(f"Min score: {min_score}")
    print(f"Already processed: {len(visited_set)}")
    print(f"{'='*60}\n")

    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
    if not ensure_logged_in(session):
        print("❌ Could not log in, aborting")
        close_session(session, save_cookies=False)
        return

    page = session.page

    # --- Set up hover-based profile API interception ---
    # While scraping comments we hover over username links.
    # Instagram fires /api/v1/users/web_profile_info/?username=X on hover.
    # We intercept those responses here — giving us full profile data
    # (followers, bio, private flag, etc.) with zero extra page navigation.
    intercepted_profiles: dict = {}

    def _on_response(response):
        url = response.url
        if '/api/v1/users/web_profile_info/' not in url:
            return
        try:
            data = response.json()
            user = (data.get('data', {}).get('user')
                    or data.get('graphql', {}).get('user')
                    or {})
            uname = user.get('username', '')
            if uname:
                intercepted_profiles[uname] = _parse_api_user(user)
        except Exception:
            pass

    page.on('response', _on_response)
    print(f"📡 Profile API interception active (hover → no page visits needed)")

    # --- PHASE 1: Scrape commenters (or resume from checkpoint) ---
    saved_commenters = checkpoint.get("scraped_commenters", {})
    if saved_commenters:
        # Resume: we already have scraped commenters from a previous run
        fresh_from_saved = [u for u in saved_commenters.keys() if u not in visited_set]
        if len(fresh_from_saved) >= count:
            print(f"📋 Resuming from checkpoint: {len(fresh_from_saved)} unvisited commenters available, skipping Phase 1")
            all_commenters = saved_commenters
        else:
            print(f"📋 Checkpoint has {len(fresh_from_saved)} unvisited, need {count} — scraping more...")
            saved_commenters = {}  # re-scrape fresh

    if not saved_commenters:
        print(f"\n--- PHASE 1: Scraping commenters (target: {count}) ---\n")
        all_commenters = {}

        for creator in creators:
            try:
                commenters = scrape_creator(page, creator, max_posts)
                all_commenters.update(commenters)
                print(f"   Running total: {len(all_commenters)} unique commenters")
            except Exception as e:
                print(f"❌ Error scraping @{creator}: {e}")

            # Check if we have enough FRESH (unvisited) commenters
            fresh_so_far = [u for u in all_commenters.keys() if u not in visited_set]
            if len(fresh_so_far) >= count:
                print(f"\n✅ Reached {count} fresh usernames — stopping early")
                break

            if creator != creators[-1]:
                wait = random.uniform(45, 90)
                print(f"⏳ Waiting {wait:.0f}s before next creator...")
                time.sleep(wait)

        # SAVE scraped commenters to disk (crash-safe)
        checkpoint["scraped_commenters"] = all_commenters
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, ensure_ascii=False)
        print(f"💾 Saved {len(all_commenters)} scraped commenters to checkpoint")

    # Filter out already-visited, then take 'count' fresh ones
    fresh = [u for u in all_commenters.keys() if u not in visited_set]
    usernames_list = fresh[:count]
    print(f"\n--- PHASE 1 DONE: {len(usernames_list)} fresh usernames to process (skipped {len(all_commenters) - len(fresh)} already visited) ---\n")

    if not usernames_list:
        print("❌ No fresh usernames to process! Try scraping different creators.")
        close_session(session, save_cookies=True)
        return

    # --- PHASE 2+3 MERGED: Profile data → pre-filter → Gemini score → save ---
    intercepted_count = len([u for u in usernames_list if u in intercepted_profiles])
    fallback_count = len(usernames_list) - intercepted_count
    print(f"--- PHASE 2+3: Filter + score ({AI_BATCH_SIZE} per batch) ---")
    print(f"    📡 {intercepted_count}/{len(usernames_list)} profiles already captured via hover API")
    print(f"    🌐 {fallback_count} profiles need page navigation (fallback)\n")

    targets = []
    total_filtered = 0
    total_females = 0
    total_low = 0
    total_visited = 0
    total_from_hover = 0
    total_from_nav = 0
    filter_reasons = {}

    # Process in chunks of AI_BATCH_SIZE
    for chunk_start in range(0, len(usernames_list), AI_BATCH_SIZE):
        chunk_usernames = usernames_list[chunk_start:chunk_start + AI_BATCH_SIZE]
        chunk_num = chunk_start // AI_BATCH_SIZE + 1
        total_chunks = (len(usernames_list) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE

        print(f"\n   === Batch {chunk_num}/{total_chunks} ({len(chunk_usernames)} usernames) ===")

        # Step A: Collect profile data — hover interception first, page nav fallback
        batch_profiles = []
        batch_comments = {}
        nav_needed = []  # usernames that weren't intercepted

        for username in chunk_usernames:
            visited_set.add(username)
            total_visited += 1

            if username in intercepted_profiles:
                # ✅ Fast path: data already collected during comment hover
                profile_data = intercepted_profiles[username]
                total_from_hover += 1
            else:
                nav_needed.append(username)
                profile_data = None   # will fill in below

            if profile_data:
                comment = all_commenters.get(username, {}).get('comment', '')
                keep, reason = pre_filter_profile(profile_data, comment)
                if keep:
                    batch_profiles.append(profile_data)
                    batch_comments[username] = comment
                else:
                    total_filtered += 1
                    key = reason.split("'")[0].strip() if "'" in reason else reason
                    filter_reasons[key] = filter_reasons.get(key, 0) + 1
                    print(f"      ✂️ @{username} — {reason}")

        # 🌐 Fallback: navigate to profiles that weren't intercepted
        if nav_needed:
            print(f"   🌐 Navigating to {len(nav_needed)} profiles (not in hover cache)...")
            for i, username in enumerate(nav_needed):
                profile_data = get_profile_data(page, username)
                total_from_nav += 1

                if not profile_data:
                    continue

                comment = all_commenters.get(username, {}).get('comment', '')
                keep, reason = pre_filter_profile(profile_data, comment)
                if keep:
                    batch_profiles.append(profile_data)
                    batch_comments[username] = comment
                else:
                    total_filtered += 1
                    key = reason.split("'")[0].strip() if "'" in reason else reason
                    filter_reasons[key] = filter_reasons.get(key, 0) + 1
                    print(f"      ✂️ @{username} — {reason}")

                if i < len(nav_needed) - 1:
                    human_delay(4, 8)

        # Rate limit break between chunks (only relevant when doing fallback nav)
        if nav_needed and chunk_start > 0 and chunk_start % (AI_BATCH_SIZE * 2) == 0:
            wait = random.uniform(20, 40)
            print(f"   ⏳ Rate limit break ({wait:.0f}s)...")
            time.sleep(wait)

        # Longer cooldown every 100 page navigations
        if total_from_nav > 0 and total_from_nav % 100 == 0:
            wait = random.uniform(60, 120)
            print(f"   🛑 Cooldown after {total_from_nav} page navigations ({wait:.0f}s)...")
            time.sleep(wait)

        # Step B: Gemini score survivors
        batch_targets = []
        if batch_profiles:
            print(f"   🤖 Scoring {len(batch_profiles)} profiles with Gemini...")
            ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
            ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

            for profile in batch_profiles:
                uname = profile['username']
                ai = ai_map.get(uname, {})
                gender = ai.get('gender', 'unknown')
                score = ai.get('score', 0)
                reasons = ai.get('reasons', 'ai_no_response')

                if gender == 'female':
                    total_females += 1
                    continue
                if score < min_score:
                    total_low += 1
                    continue

                source = all_commenters.get(uname, {})
                target = {
                    **profile,
                    "gender": gender,
                    "score": score,
                    "reasons": reasons[:150],
                    "source_creator": source.get('source_creator', ''),
                    "source_post": source.get('source_post', ''),
                    "comment": batch_comments.get(uname, '')[:100],
                    "scraped_at": datetime.now().isoformat(),
                }
                batch_targets.append(target)
                targets.append(target)

            # Step C: Save immediately after each batch
            if batch_targets:
                save_targets_csv(batch_targets, SCRAPER_OUTPUT_CSV)
                merge_to_tracker(batch_targets)
            time.sleep(2)

        # Step D: Update checkpoint after every batch (crash-safe)
        checkpoint["visited"] = list(visited_set)
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, ensure_ascii=False)

        print(f"   ✅ Batch {chunk_num}: {len(batch_targets)} qualified | Running total: {len(targets)} | Visited: {total_visited}/{len(usernames_list)}")

    close_session(session, save_cookies=True)

    # Clear checkpoint since we're done (next run will re-scrape fresh)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("🗑️ Cleared checkpoint file")

    # --- Final summary ---
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"Profiles processed: {total_visited}")
    print(f"  📡 Via hover API (fast): {total_from_hover}")
    print(f"  🌐 Via page navigation (fallback): {total_from_nav}")
    print(f"Pre-filtered out: {total_filtered}")
    for reason, cnt in sorted(filter_reasons.items(), key=lambda x: -x[1]):
        print(f"   {reason}: {cnt}")
    print(f"Sent to Gemini: {total_visited - total_filtered}")
    print(f"Gemini females excluded: {total_females}")
    print(f"Gemini low score excluded: {total_low}")
    print(f"QUALIFIED TARGETS: {len(targets)}")
    print(f"Saved to: {SCRAPER_OUTPUT_CSV}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# 8b. Score-file mode — read usernames from file, visit profiles, score
# ---------------------------------------------------------------------------

def run_score_file(score_file, min_score=None, headless=True, no_proxy=False):
    """
    Read usernames from a text file, visit each profile, score with Gemini,
    save qualified targets to CSV.
    """
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    # Read usernames from text file
    with open(score_file, 'r') as f:
        usernames = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not usernames:
        print("❌ No usernames in file!")
        return

    # Load metadata (comments/sources) if available
    comments_data = {}
    if os.path.exists(RAW_COMMENTERS_JSON):
        with open(RAW_COMMENTERS_JSON, 'r') as f:
            comments_data = json.load(f)

    print(f"\n{'='*60}")
    print(f"SCORE-FILE MODE")
    print(f"Input: {score_file} ({len(usernames)} usernames)")
    print(f"Min score: {min_score}")
    print(f"Batch size: {AI_BATCH_SIZE}")
    print(f"{'='*60}\n")

    # Init Gemini
    try:
        gemini_model = _init_gemini()
        print(f"🤖 Gemini AI ready ({GEMINI_MODEL})")
    except Exception as e:
        print(f"❌ Could not initialize Gemini: {e}")
        return

    # Open browser session
    accounts = get_all_accounts()
    if not accounts:
        print("❌ No accounts available!")
        return

    account = None
    for acc in reversed(accounts):
        cookie_file = os.path.join("sessions", f"{acc['username']}_state.json")
        if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 5000:
            account = acc
            break
    if account is None:
        account = accounts[-1]

    print(f"🔑 Using account @{account['username']}")

    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
    if not ensure_logged_in(session):
        print("❌ Could not log in, aborting")
        close_session(session, save_cookies=False)
        return

    page = session.page
    targets = []
    total_females = 0
    total_low = 0

    batch_profiles = []
    batch_comments = {}

    for i, username in enumerate(usernames):
        profile_data = get_profile_data(page, username)
        if profile_data:
            batch_profiles.append(profile_data)
            batch_comments[username] = comments_data.get(username, {}).get('comment', '')

        # Rate limiting
        if i < len(usernames) - 1:
            human_delay(4, 8)
        if i > 0 and i % 25 == 0:
            wait = random.uniform(30, 60)
            print(f"   ⏳ Rate limit break ({wait:.0f}s)...")
            time.sleep(wait)

        # Score when batch is full or last profile
        is_last = (i == len(usernames) - 1)
        if len(batch_profiles) >= AI_BATCH_SIZE or (is_last and batch_profiles):
            print(f"\n   🤖 Scoring batch ({len(batch_profiles)} profiles, {i+1}/{len(usernames)} done)...")

            ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
            ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

            batch_targets = []
            for profile in batch_profiles:
                uname = profile['username']
                ai = ai_map.get(uname, {})
                gender = ai.get('gender', 'unknown')
                score = ai.get('score', 0)
                reasons = ai.get('reasons', 'ai_no_response')

                if gender == 'female':
                    total_females += 1
                    continue
                if score < min_score:
                    total_low += 1
                    continue

                source = comments_data.get(uname, {})
                target = {
                    **profile,
                    "gender": gender,
                    "score": score,
                    "reasons": reasons[:150],
                    "source_creator": source.get('source_creator', ''),
                    "source_post": source.get('source_post', ''),
                    "comment": source.get('comment', '')[:100],
                    "scraped_at": datetime.now().isoformat(),
                }
                batch_targets.append(target)
                targets.append(target)

            if batch_targets:
                save_targets_csv(batch_targets, SCRAPER_OUTPUT_CSV)
                merge_to_tracker(batch_targets)

            print(f"   ✅ Batch: {len(batch_targets)} qualified | Total: {len(targets)}")
            batch_profiles = []
            batch_comments = {}
            time.sleep(2)

    close_session(session, save_cookies=True)

    print(f"\n{'='*60}")
    print(f"SCORING COMPLETE")
    print(f"Profiles visited: {len(usernames)}")
    print(f"Females excluded: {total_females}")
    print(f"Low score excluded: {total_low}")
    print(f"Qualified targets (score >= {min_score}): {len(targets)}")
    print(f"Saved to: {SCRAPER_OUTPUT_CSV}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# 8c. Main orchestrator (legacy all-in-one)
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

    # Pick an account that has valid cookies
    accounts = get_all_accounts()
    if not accounts:
        print("❌ No accounts available! Create one first with main.py")
        return []

    # Prefer account with existing cookie file (most likely to be logged in)
    import os as _os
    account = None
    for acc in reversed(accounts):
        cookie_file = _os.path.join("sessions", f"{acc['username']}_state.json")
        if _os.path.exists(cookie_file) and _os.path.getsize(cookie_file) > 5000:
            account = acc
            print(f"🔑 Using account @{acc['username']} (has valid cookies)")
            break
    if account is None:
        account = accounts[-1]
        print(f"⚠️ No account with valid cookies, trying @{account['username']}")

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

    # --- Phase 2+3: Collect profiles in batches → score → save immediately ---
    targets = []
    total_profiles_collected = 0
    total_females_excluded = 0
    total_low_score = 0

    if score_profiles and all_commenters:
        usernames = list(all_commenters.keys())
        print(f"📊 Processing {len(usernames)} profiles (batch size: {AI_BATCH_SIZE})...\n")

        batch_profiles = []
        batch_comments = {}

        for i, username in enumerate(usernames):
            # Collect profile data
            profile_data = get_profile_data(page, username)
            if profile_data:
                batch_profiles.append(profile_data)
                batch_comments[username] = all_commenters[username].get('comment', '')
                total_profiles_collected += 1

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

            # When batch is full OR last profile — score and save immediately
            is_last = (i == len(usernames) - 1)
            if len(batch_profiles) >= AI_BATCH_SIZE or (is_last and batch_profiles):
                batch_num = (total_profiles_collected // AI_BATCH_SIZE) + (1 if is_last else 0)
                print(f"\n   🤖 Scoring batch ({len(batch_profiles)} profiles, {total_profiles_collected}/{len(usernames)} total)...")

                ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
                ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

                batch_targets = []
                for profile in batch_profiles:
                    uname = profile['username']
                    ai = ai_map.get(uname, {})
                    gender = ai.get('gender', 'unknown')
                    score = ai.get('score', 0)
                    reasons = ai.get('reasons', 'ai_no_response')

                    if gender == 'female':
                        total_females_excluded += 1
                        continue
                    if score < min_score:
                        total_low_score += 1
                        continue

                    target = {
                        **profile,
                        "gender": gender,
                        "score": score,
                        "reasons": reasons[:150],
                        "source_creator": all_commenters.get(uname, {}).get('source_creator', ''),
                        "source_post": all_commenters.get(uname, {}).get('source_post', ''),
                        "comment": batch_comments.get(uname, '')[:100],
                        "scraped_at": datetime.now().isoformat(),
                    }
                    batch_targets.append(target)
                    targets.append(target)

                # SAVE IMMEDIATELY after each batch — never lose progress
                if batch_targets:
                    save_targets_csv(batch_targets, SCRAPER_OUTPUT_CSV)
                    merge_to_tracker(batch_targets)

                print(f"   ✅ Batch done: {len(batch_targets)} qualified, {len(targets)} total so far")

                # Clear batch for next round
                batch_profiles = []
                batch_comments = {}
                time.sleep(2)  # Rate limit between API calls

        print(f"\n   ✅ Finished: {total_profiles_collected} profiles processed")

    elif not score_profiles:
        # No scoring — keep all commenters with default score
        no_score_targets = []
        for username, data in all_commenters.items():
            target = {
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
            }
            no_score_targets.append(target)
            targets.append(target)

        if no_score_targets:
            save_targets_csv(no_score_targets, SCRAPER_OUTPUT_CSV)
            merge_to_tracker(no_score_targets)

    close_session(session, save_cookies=True)

    # --- Final summary ---
    print(f"\n{'='*60}")
    print(f"SCRAPER RESULTS")
    print(f"Total commenters found: {len(all_commenters)}")
    print(f"Profiles collected: {total_profiles_collected}")
    print(f"Females excluded: {total_females_excluded}")
    print(f"Low score excluded: {total_low_score}")
    print(f"AI-qualified targets (score >= {min_score}): {len(targets)}")
    print(f"{'='*60}\n")

    return targets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape high-intent targets from competitor creators")
    parser.add_argument("--creators", nargs="+", help="Creator handles to scrape")
    parser.add_argument("--posts", type=int, default=None, help="Posts per creator (default: 12)")
    parser.add_argument("--no-score", action="store_true", help="Skip profile scoring")
    parser.add_argument("--min-score", type=int, default=None, help="Min quality score 0-10 (default: 4)")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--no-proxy", action="store_true", help="Direct connection (no proxy)")

    # New 3-step workflow
    parser.add_argument("--scrape-only", action="store_true",
                        help="Step 1: Just scrape usernames → raw_commenters.txt")
    parser.add_argument("--count", type=int, default=50,
                        help="How many usernames to collect (for --scrape-only, default: 50)")
    parser.add_argument("--score-file", type=str, default=None,
                        help="Step 3: Score usernames from file (e.g. raw_commenters.txt)")
    args = parser.parse_args()

    if args.scrape_only:
        run_scrape_only(
            creators=args.creators,
            max_posts=args.posts,
            count=args.count,
            headless=not args.visible,
            no_proxy=args.no_proxy,
            min_score=args.min_score,
        )
    elif args.score_file:
        run_score_file(
            score_file=args.score_file,
            min_score=args.min_score,
            headless=not args.visible,
            no_proxy=args.no_proxy,
        )
    else:
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
