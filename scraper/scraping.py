"""
Scraping functions — extract post links and commenters from Instagram.
"""

import random
import time

from core.utils import human_delay

# Usernames to skip during hover interception
HOVER_NOISE = {
    'instagram', 'explore', 'accounts', 'reels', 'stories',
    'direct', 'p', 'about', 'help', 'press', 'api', 'jobs',
    'privacy', 'terms', 'locations', 'directory',
}


def get_post_links(page, creator, max_posts=9):
    """
    Navigate to a creator's profile and collect post URLs.

    Returns:
        list of post URLs (e.g. /p/ABC123/)
    """
    print(f"\nScraping posts from @{creator}...")
    page.goto(f"https://www.instagram.com/{creator}/", wait_until="domcontentloaded", timeout=30000)
    human_delay(6, 9)

    current_url = page.url
    title = page.title()
    print(f"   URL: {current_url}")
    print(f"   Title: {title}")

    page_debug = page.evaluate("""() => {
        const text = document.body.innerText.substring(0, 500);
        const allHrefs = Array.from(document.querySelectorAll('a[href]')).map(a => a.getAttribute('href')).slice(0, 30);
        return {bodyPreview: text, hrefs: allHrefs};
    }""")
    print(f"   Body preview: {page_debug.get('bodyPreview', '')[:200]}")
    print(f"   First hrefs: {page_debug.get('hrefs', [])[:10]}")

    for scroll in range(4):
        page.mouse.wheel(0, 1200)
        human_delay(2, 3)

    links = page.evaluate(r"""() => {
        const hrefs = new Set();

        document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]').forEach(a => {
            const href = a.getAttribute('href');
            if (href) hrefs.add(href);
        });

        if (hrefs.size === 0) {
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.getAttribute('href');
                if (href && (/\/p\/[A-Za-z0-9_-]+/.test(href) || /\/reel\/[A-Za-z0-9_-]+/.test(href))) {
                    hrefs.add(href);
                }
            });
        }

        const totalAnchors = document.querySelectorAll('a').length;
        return {links: [...hrefs], totalAnchors: totalAnchors};
    }""")

    total_anchors = links.get('totalAnchors', 0)
    links = links.get('links', [])[:max_posts]
    print(f"   Total anchors on page: {total_anchors}")
    print(f"   Found {len(links)} posts")
    return links


def scrape_post_commenters(page, post_path):
    """
    Navigate to a post and extract commenter usernames.

    Returns:
        list of dicts: [{"username": "...", "comment": "..."}, ...]
    """
    url = f"https://www.instagram.com{post_path}"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    human_delay(3, 5)

    try:
        view_all = page.locator('span:has-text("View all")').first
        if view_all.is_visible(timeout=5000):
            view_all.click()
            human_delay(3, 5)
    except:
        pass

    for _ in range(3):
        try:
            page.mouse.wheel(0, 600)
            human_delay(1, 2)
        except:
            break

    for _ in range(3):
        try:
            more_btn = page.locator('button svg[aria-label="Load more comments"]').first
            if more_btn.is_visible(timeout=2000):
                more_btn.click()
                human_delay(2, 3)
        except:
            break

    commenters = page.evaluate("""() => {
        const results = [];
        const seen = new Set();

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

    noise = {'instagram', 'explore', 'about', 'help', 'press', 'api', 'jobs', 'privacy', 'terms', 'locations', 'directory'}
    commenters = [c for c in commenters if c['username'].lower() not in noise and len(c['username']) > 2]

    print(f"   Post {post_path[:20]}... -> {len(commenters)} commenters")

    # Hover over visible comment author links to trigger profile API calls
    try:
        target_usernames = {c['username'] for c in commenters}
        links = page.locator('ul li a[href^="/"], article a[href^="/"]').all()
        hovered = 0
        for link in links:
            try:
                href = (link.get_attribute('href', timeout=500) or '').strip('/')
                if (href and href not in HOVER_NOISE and '/' not in href
                        and href in target_usernames):
                    link.scroll_into_view_if_needed()
                    link.hover(timeout=2000)
                    time.sleep(0.35)
                    hovered += 1
                    if hovered >= 30:
                        break
            except Exception:
                continue
        if hovered:
            page.mouse.move(10, 10)
            time.sleep(0.3)
            print(f"   Hovered {hovered} links (profile data collected via API)")
    except Exception:
        pass

    return commenters


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
            print(f"   Error scraping {link}: {e}")

        if i < len(post_links) - 1:
            human_delay(8, 15)

    print(f"   @{creator}: {len(all_commenters)} unique commenters")
    return all_commenters
