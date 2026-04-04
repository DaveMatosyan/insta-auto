"""
Browser-based DM operations via Playwright.
Replaces instagrapi direct_send / direct_messages with real browser interactions.
"""

import time
import random
from datetime import datetime, timezone

from core.utils import human_delay


# --- Selectors ---
DM_INBOX_URL = "https://www.instagram.com/direct/inbox/"
DM_NEW_URL = "https://www.instagram.com/direct/new/"
NAV_TIMEOUT = 30000
ELEMENT_TIMEOUT = 15000


def _dismiss_notifications_popup(page):
    """Dismiss 'Turn on Notifications' popup if it appears."""
    try:
        not_now = page.locator('button:has-text("Not Now")').first
        if not_now.is_visible(timeout=3000):
            not_now.click()
            human_delay(1, 2)
    except Exception:
        pass


def _navigate_to_inbox(page):
    """Navigate to DM inbox if not already there."""
    if "/direct/" not in page.url:
        page.goto(DM_INBOX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(2, 4)
        _dismiss_notifications_popup(page)


def send_dm(page, target_username, text):
    """
    Send a direct message to a target user via browser.

    Flow:
      1. Navigate to target's profile
      2. Click the "Message" button to open DM thread
      3. Type message and send

    Args:
        page: Playwright Page (logged in)
        target_username: who to message
        text: message content

    Returns:
        bool: True if sent successfully
    """
    try:
        # Step 1: Go to target's profile
        page.goto(f"https://www.instagram.com/{target_username}/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)
        _dismiss_notifications_popup(page)

        # Step 2: Click Message button on profile
        msg_clicked = False
        for selector in [
            'div[role="button"]:has-text("Message")',
            'button:has-text("Message")',
            'a:has-text("Message")',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn.click()
                    msg_clicked = True
                    print(f"  [dm] Clicked Message on @{target_username}'s profile")
                    break
            except Exception:
                continue

        if not msg_clicked:
            # JS fallback
            msg_clicked = page.evaluate("""
                () => {
                    const els = document.querySelectorAll('div[role="button"], button, a');
                    for (const el of els) {
                        if (el.textContent?.trim() === 'Message' && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)

        if not msg_clicked:
            print(f"  [dm] Could not find Message button on @{target_username}'s profile")
            return False

        # Wait for DM thread to load — either URL changes to /direct/ or input appears
        human_delay(2, 3)
        for _ in range(10):
            if "/direct/" in page.url:
                break
            # Check if a textbox appeared (overlay mode)
            try:
                tb = page.locator('div[role="textbox"][contenteditable], textarea[placeholder*="Message"]').first
                if tb.is_visible(timeout=1000):
                    break
            except Exception:
                pass
            human_delay(1, 1.5)
        human_delay(1, 2)
        _dismiss_notifications_popup(page)

        # Step 3: Find message input and type
        msg_input = None
        for selector in [
            'textarea[placeholder="Message..."]',
            'textarea[placeholder*="Message"]',
            'div[role="textbox"][contenteditable]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
            'textarea[aria-label*="Message"]',
            'textarea',
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=5000):
                    msg_input = el
                    break
            except Exception:
                continue

        if not msg_input:
            # JS fallback: focus any editable element
            found = page.evaluate("""
                () => {
                    const editables = document.querySelectorAll('[contenteditable="true"], textarea');
                    for (const el of editables) {
                        if (el.offsetParent !== null && el.offsetHeight > 10) {
                            el.focus();
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if found:
                human_delay(0.5, 1)
                page.keyboard.type(text, delay=random.randint(20, 50))
                human_delay(0.5, 1.5)
                page.keyboard.press("Enter")
                human_delay(1, 2)
                print(f"  [dm] Sent to @{target_username}: {text[:60]}{'...' if len(text) > 60 else ''}")
                return True

            print(f"  [dm] Could not find message input field")
            print(f"  [dm] Current URL: {page.url}")
            return False

        msg_input.click()
        human_delay(0.5, 1)

        # Type character by character for realism
        page.keyboard.type(text, delay=random.randint(20, 50))
        human_delay(0.5, 1.5)

        # Send: press Enter or click Send button
        sent = False
        try:
            send_btn = page.locator('button:has-text("Send"), div[role="button"]:has-text("Send")').first
            if send_btn.is_visible(timeout=3000):
                send_btn.click()
                sent = True
        except Exception:
            pass

        if not sent:
            page.keyboard.press("Enter")

        human_delay(1, 2)
        print(f"  [dm] Sent to @{target_username}: {text[:60]}{'...' if len(text) > 60 else ''}")
        return True

    except Exception as e:
        print(f"  [dm] Error sending to @{target_username}: {e}")
        return False


def _open_thread(page, target_username):
    """
    Open a DM thread with a specific user.

    Goes to the user's profile and clicks Message button.
    Returns True if thread was opened.
    """
    try:
        page.goto(f"https://www.instagram.com/{target_username}/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 4)
        _dismiss_notifications_popup(page)

        # Click Message button
        for selector in [
            'div[role="button"]:has-text("Message")',
            'button:has-text("Message")',
            'a:has-text("Message")',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn.click()
                    human_delay(3, 5)
                    _dismiss_notifications_popup(page)
                    return True
            except Exception:
                continue

        # JS fallback
        clicked = page.evaluate("""
            () => {
                const els = document.querySelectorAll('div[role="button"], button, a');
                for (const el of els) {
                    if (el.textContent?.trim() === 'Message' && el.offsetParent !== null) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            human_delay(3, 5)
            _dismiss_notifications_popup(page)
            return True

        print(f"  [dm] Could not find Message button for @{target_username}")
        return False

    except Exception as e:
        print(f"  [dm] Error opening thread with @{target_username}: {e}")
        return False


def read_thread_messages(page, target_username, limit=20):
    """
    Read messages from a DM thread with a specific user via browser.

    Args:
        page: Playwright Page
        target_username: the other person
        limit: max messages to return

    Returns:
        list of dicts: [{"text": str, "from": "us"|"them", "timestamp": datetime}]
    """
    try:
        if not _open_thread(page, target_username):
            return []

        human_delay(1, 2)

        # Scrape message bubbles from the thread
        # Instagram DM messages are typically in div elements within the thread
        messages = page.evaluate("""
            (limit) => {
                const msgs = [];
                // Instagram DM messages are inside the thread container
                // Each message has a different structure for sent vs received
                const msgElements = document.querySelectorAll(
                    'div[role="row"], div[class*="message"], div[data-testid*="message"]'
                );

                // Fallback: look for text content in the chat area
                if (msgElements.length === 0) {
                    const chatArea = document.querySelector('div[role="grid"], section main');
                    if (chatArea) {
                        const allDivs = chatArea.querySelectorAll('div > span, div > div > span');
                        for (const span of allDivs) {
                            const text = span.textContent?.trim();
                            if (text && text.length > 0 && text.length < 2000) {
                                // Try to determine direction by position/style
                                const rect = span.getBoundingClientRect();
                                const parent = span.closest('div[class]');
                                const style = parent ? window.getComputedStyle(parent) : null;

                                msgs.push({
                                    text: text,
                                    from: "unknown",
                                    timestamp: new Date().toISOString(),
                                });
                            }
                            if (msgs.length >= limit) break;
                        }
                    }
                }

                for (const el of msgElements) {
                    const text = el.textContent?.trim();
                    if (!text || text.length === 0) continue;

                    // Determine direction: sent messages typically align right
                    const rect = el.getBoundingClientRect();
                    const viewportWidth = window.innerWidth;
                    const direction = rect.left > viewportWidth * 0.4 ? "us" : "them";

                    msgs.push({
                        text: text,
                        from: direction,
                        timestamp: new Date().toISOString(),
                    });

                    if (msgs.length >= limit) break;
                }

                return msgs;
            }
        """, limit)

        result = []
        for msg in messages:
            result.append({
                "text": msg["text"],
                "from": msg["from"],
                "timestamp": datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00")),
            })

        return result

    except Exception as e:
        print(f"  [dm] Error reading thread with @{target_username}: {e}")
        return []


def get_last_message_from_them(page, target_username):
    """
    Get the most recent message from the target in a DM thread.

    Returns:
        str or None
    """
    messages = read_thread_messages(page, target_username, limit=10)
    for msg in reversed(messages):
        if msg["from"] == "them":
            return msg["text"]
    return None


def get_unread_threads(page):
    """
    Get DM threads with unread messages from other users.

    Returns:
        list of dicts: [{"username": str, "last_message": str}]
    """
    try:
        _navigate_to_inbox(page)
        human_delay(2, 3)

        # Scrape threads from inbox — unread threads typically have bold text or a dot indicator
        threads = page.evaluate("""
            () => {
                const results = [];
                // Look for thread items in the inbox list
                const threadElements = document.querySelectorAll(
                    'div[role="listitem"], a[href*="/direct/t/"]'
                );

                for (const el of threadElements) {
                    const text = el.textContent || '';
                    // Check for unread indicator (bold text, blue dot, etc.)
                    const hasUnread = el.querySelector(
                        '[aria-label*="unread"], span[style*="font-weight: 600"], ' +
                        'div[style*="background-color: rgb(0, 149, 246)"]'
                    );

                    if (hasUnread || el.querySelector('span[style*="font-weight"]')) {
                        // Extract username from the thread element
                        const nameEl = el.querySelector('span[dir="auto"]');
                        const username = nameEl ? nameEl.textContent.trim() : '';

                        // Extract last message preview
                        const previewEls = el.querySelectorAll('span[dir="auto"]');
                        let lastMsg = '';
                        if (previewEls.length > 1) {
                            lastMsg = previewEls[previewEls.length - 1].textContent.trim();
                        }

                        if (username) {
                            results.push({
                                username: username,
                                last_message: lastMsg,
                            });
                        }
                    }
                }

                return results;
            }
        """)

        return threads

    except Exception as e:
        print(f"  [dm] Error getting unread threads: {e}")
        return []


def get_our_username(page):
    """Get the logged-in user's username from the page."""
    try:
        # Try reading from profile link in nav
        username = page.evaluate(r"""
            () => {
                // Check for profile link in navigation
                const profileLink = document.querySelector('a[href*="/"][role="link"] img[alt]');
                if (profileLink) {
                    const alt = profileLink.getAttribute('alt');
                    if (alt && !alt.includes(' ')) return alt;
                }

                // Check URL if on profile page
                const path = window.location.pathname;
                if (path.match(/^\/[^/]+\/?$/) && !['/', '/explore/', '/direct/', '/accounts/'].some(p => path.startsWith(p))) {
                    return path.replace(/\//g, '');
                }

                // Try meta tags
                const meta = document.querySelector('meta[property="og:title"]');
                if (meta) {
                    const match = meta.content.match(/@(\w+)/);
                    if (match) return match[1];
                }

                return null;
            }
        """)
        return username
    except Exception as e:
        print(f"  [dm] Error getting username: {e}")
        return None
