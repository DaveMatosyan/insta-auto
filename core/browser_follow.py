"""
Browser-based follow operations via Playwright.
Replaces instagrapi user_follow / user_followers with real browser interactions.
"""

import time
import random

from core.utils import human_delay


NAV_TIMEOUT = 30000
ELEMENT_TIMEOUT = 15000


def follow_user(page, target_username):
    """
    Follow a user by navigating to their profile and clicking Follow.

    Args:
        page: Playwright Page (logged in)
        target_username: username to follow

    Returns:
        bool: True if followed successfully
    """
    try:
        page.goto(f"https://www.instagram.com/{target_username}/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(2, 4)

        # Check if profile exists
        if "Sorry, this page isn't available" in (page.text_content("body") or ""):
            print(f"  [follow] @{target_username} not found")
            return False

        # Check if already following
        following_btn = page.locator('button:has-text("Following"), div[role="button"]:has-text("Following")').first
        try:
            if following_btn.is_visible(timeout=2000):
                print(f"  [follow] Already following @{target_username}")
                return True
        except Exception:
            pass

        # Click Follow button
        for selector in [
            'button:has-text("Follow")',
            'div[role="button"]:has-text("Follow")',
            'header button:has-text("Follow")',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn_text = btn.inner_text().strip()
                    # Make sure it's "Follow" not "Following" or "Follow Back"
                    if btn_text in ("Follow", "Follow Back"):
                        btn.click()
                        human_delay(1, 3)
                        print(f"  [follow] Followed @{target_username}")
                        return True
            except Exception:
                continue

        print(f"  [follow] Could not find Follow button for @{target_username}")
        return False

    except Exception as e:
        print(f"  [follow] Error following @{target_username}: {e}")
        return False


def check_is_following_us(page, target_username):
    """
    Check if a target user follows us using Instagram's web API.
    Fetches user ID first, then checks friendship status.

    Args:
        page: Playwright Page (logged in)
        target_username: username to check

    Returns:
        bool: True if they follow us
    """
    try:
        result = page.evaluate(r"""
            async (username) => {
                try {
                    // Get user ID from web profile API
                    const userResp = await fetch(
                        '/api/v1/users/web_profile_info/?username=' + username,
                        { headers: { 'X-IG-App-ID': '936619743392459' } }
                    );
                    if (!userResp.ok) return { error: 'user_lookup_' + userResp.status };
                    const userData = await userResp.json();
                    const userId = userData?.data?.user?.id;
                    if (!userId) return { error: 'no_user_id' };

                    // Check friendship status
                    const friendResp = await fetch(
                        '/api/v1/friendships/show/' + userId + '/',
                        { headers: { 'X-IG-App-ID': '936619743392459' } }
                    );
                    if (!friendResp.ok) return { error: 'friendship_' + friendResp.status };
                    const data = await friendResp.json();
                    return { followed_by: data.followed_by, following: data.following };
                } catch(e) {
                    return { error: e.message };
                }
            }
        """, target_username)

        if result.get("error"):
            print(f"  [follow] API error checking @{target_username}: {result['error']}")
            return False

        return result.get("followed_by", False)

    except Exception as e:
        print(f"  [follow] Error checking if @{target_username} follows us: {e}")
        return False


def get_followers_list(page, username, max_count=200):
    """
    Get a list of follower usernames by opening the followers modal.

    Args:
        page: Playwright Page (logged in)
        username: whose followers to get
        max_count: max followers to collect

    Returns:
        set of usernames
    """
    try:
        page.goto(f"https://www.instagram.com/{username}/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(2, 4)

        # Click on followers count to open modal
        followers_link = page.locator(f'a[href="/{username}/followers/"]').first
        try:
            if followers_link.is_visible(timeout=5000):
                followers_link.click()
                human_delay(2, 3)
        except Exception:
            # Try direct navigation
            page.goto(f"https://www.instagram.com/{username}/followers/",
                      wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            human_delay(2, 3)

        # Scroll and collect usernames from the modal
        collected = set()
        last_count = 0
        stale_rounds = 0

        for _ in range(50):  # max 50 scroll rounds
            # Scrape visible usernames in the modal
            usernames = page.evaluate("""
                () => {
                    const names = [];
                    // Followers modal has a scrollable list
                    const items = document.querySelectorAll(
                        'div[role="dialog"] a[href^="/"], ' +
                        'div[role="dialog"] span[dir="auto"]'
                    );
                    for (const item of items) {
                        let username = '';
                        if (item.tagName === 'A') {
                            username = item.getAttribute('href')?.replace(/\\//g, '') || '';
                        } else {
                            username = item.textContent?.trim() || '';
                        }
                        // Filter: valid username (no spaces, not empty, not a display name)
                        if (username && !username.includes(' ') && username.length > 0
                            && username.length < 31 && /^[a-zA-Z0-9._]+$/.test(username)) {
                            names.push(username);
                        }
                    }
                    return [...new Set(names)];
                }
            """)

            for u in usernames:
                collected.add(u)

            if len(collected) >= max_count:
                break

            if len(collected) == last_count:
                stale_rounds += 1
                if stale_rounds >= 3:
                    break
            else:
                stale_rounds = 0
                last_count = len(collected)

            # Scroll the modal
            page.evaluate("""
                () => {
                    const modal = document.querySelector('div[role="dialog"] div[style*="overflow"]');
                    if (modal) modal.scrollTop += 600;
                }
            """)
            human_delay(1, 2)

        # Close modal
        try:
            close_btn = page.locator('div[role="dialog"] button[aria-label="Close"], svg[aria-label="Close"]').first
            if close_btn.is_visible(timeout=3000):
                close_btn.click()
                human_delay(1, 2)
        except Exception:
            page.keyboard.press("Escape")

        return collected

    except Exception as e:
        print(f"  [follow] Error getting followers for @{username}: {e}")
        return set()
