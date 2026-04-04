"""
Continuous DM bot — sits in the inbox, watches for new messages, replies with AI.

Usage:
    python run_dm_loop.py --headed --interval 15
"""

import argparse
import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone, timedelta

from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.browser_dm import send_dm, _dismiss_notifications_popup
from core.utils import human_delay
from dm.storage import (
    get_active_conversations, get_pending_conversations,
    get_conversation_with_history, log_message, update_conversation,
    get_conversations_needing_reply, check_existing_conversation,
    create_conversation, get_target_profile,
)
from dm.conversation import init_gemini, generate_opener, generate_reply, classify_reply, calculate_reply_delay
from dm.ramp import get_all_dm_accounts, record_dm_sent, reset_daily_dm_counts


DM_INBOX_URL = "https://www.instagram.com/direct/inbox/"
NAV_TIMEOUT = 30000


def _go_to_inbox(page):
    """Navigate to DM inbox."""
    if "/direct/inbox" not in page.url:
        page.goto(DM_INBOX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)
        _dismiss_notifications_popup(page)


def _detect_unread_threads(page):
    """
    Detect threads with unread messages in the inbox.
    Works on both mobile and desktop Instagram DOM:
      - Mobile: div[role="button"] with hidden <div>Unread</div> (offsetWidth < 2)
      - Desktop: button elements with visible "Unread" text or "N new messages"

    Returns list of dicts: [{"display_name": str, "index": int}]
    """
    return page.evaluate(r"""
        () => {
            const unread = [];

            // Find all thread items — can be button or div[role="button"]
            const allButtons = document.querySelectorAll('button, div[role="button"]');
            let threadIndex = 0;

            for (const btn of allButtons) {
                // Only consider elements that have a profile pic (thread items)
                const pics = btn.querySelectorAll('img[alt="user-profile-picture"]');
                if (pics.length === 0) continue;

                // Check for "Unread" marker — multiple detection methods
                let hasUnread = false;
                const allEls = btn.querySelectorAll('*');
                for (const el of allEls) {
                    const text = el.textContent?.trim();
                    // Method 1: hidden div with "Unread" text (mobile)
                    if (text === 'Unread' && el.childNodes.length <= 2) {
                        hasUnread = true;
                        break;
                    }
                    // Method 2: "N new messages" text (desktop)
                    if (text && text.match(/^\d+ new message/)) {
                        hasUnread = true;
                        break;
                    }
                }

                if (hasUnread) {
                    // Get display name — first meaningful text in the thread
                    let displayName = '';
                    const candidates = btn.querySelectorAll('span, div');
                    for (const c of candidates) {
                        const t = c.textContent?.trim();
                        if (t && t.length > 0 && t.length < 30
                            && t !== 'Unread' && t !== '·'
                            && !t.startsWith('You:')
                            && !t.match(/^\d+ new message/)
                            && !t.match(/^\d+[mhd]$/)
                            && !t.match(/^\d+ (minutes?|hours?|days?) ago/)
                            && c.offsetWidth > 0
                            && c.children.length === 0) {
                            displayName = t;
                            break;
                        }
                    }
                    unread.push({ display_name: displayName, index: threadIndex });
                }
                threadIndex++;
            }

            return unread;
        }
    """)


def _click_thread_by_index(page, thread_index):
    """Click on a thread in the inbox by its index. Returns True if clicked."""
    clicked = page.evaluate("""
        (idx) => {
            const allButtons = document.querySelectorAll('button, div[role="button"]');
            let threadIndex = 0;
            for (const btn of allButtons) {
                const pics = btn.querySelectorAll('img[alt="user-profile-picture"], img[draggable="false"]');
                if (pics.length === 0) continue;
                if (threadIndex === idx) {
                    btn.click();
                    return true;
                }
                threadIndex++;
            }
            return false;
        }
    """, thread_index)
    if clicked:
        human_delay(3, 5)
    return clicked


def _extract_username_from_thread(page):
    """
    Extract the actual username from an open DM thread.
    Works on both mobile and desktop DOM.
    Returns username string or None.
    """
    return page.evaluate(r"""
        () => {
            // Method 1: link with "Open the profile page of" aria-label
            const links = document.querySelectorAll('a[href]');
            for (const a of links) {
                const label = a.getAttribute('aria-label') || '';
                if (label.startsWith('Open the profile page of ')) {
                    return label.replace('Open the profile page of ', '').trim();
                }
            }

            // Method 2: extract from href pattern /<username>/
            // Look for profile links in the chat header area (skip nav links)
            const navPaths = new Set(['direct', 'explore', 'reels', 'accounts', 'p', 'stories',
                'notifications', 'settings', 'create', 'about', 'legal', 'safety']);
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const match = href.match(/^\/([a-zA-Z0-9._]+)\/$/);
                if (match && !navPaths.has(match[1])) {
                    const rect = a.getBoundingClientRect();
                    if (rect.top < 200 && rect.top > 0) {
                        return match[1];
                    }
                }
            }

            // Method 3: fallback — any profile link not in nav
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const match = href.match(/^\/([a-zA-Z0-9._]+)\/$/);
                if (match && !navPaths.has(match[1])) {
                    return match[1];
                }
            }

            // Method 4: thread header — look for username-like text in the header area
            // On mobile, the header shows the display name; look for smaller text that looks like a username
            const headerEls = document.querySelectorAll('h2, h1, heading, [role="heading"]');
            for (const h of headerEls) {
                const t = h.textContent?.trim();
                if (t && t.match(/^[a-zA-Z0-9._]+$/) && t.length > 2 && t.length < 30) {
                    if (!navPaths.has(t)) return t;
                }
            }

            return null;
        }
    """)


def _resolve_username_from_display_name(display_name, bot_username):
    """
    Look up an Instagram username from a display name using Supabase conversations.
    This is a fallback when DOM parsing can't find the username directly.
    Returns username string or None.
    """
    try:
        from db.supabase_client import supabase
        # Search conversations for this bot account — match target display name
        result = supabase.table("conversations").select(
            "target_username"
        ).eq("account_username", bot_username).execute()

        if not result.data:
            return None

        # Try to match by checking profiles for display name
        for conv in result.data:
            target = conv.get("target_username", "")
            # Quick heuristic: if display name is contained in username or vice versa
            if display_name.lower().replace(" ", "") in target.lower().replace(".", "").replace("_", ""):
                return target
            if target.lower().replace(".", "").replace("_", "") in display_name.lower().replace(" ", ""):
                return target

        # Broader search: check target_profiles table
        for conv in result.data:
            target = conv.get("target_username", "")
            try:
                profile = supabase.table("target_profiles").select(
                    "full_name"
                ).eq("username", target).single().execute()
                if profile.data:
                    full_name = (profile.data.get("full_name") or "").strip()
                    if full_name.lower() == display_name.lower():
                        return target
            except Exception:
                continue

        return None
    except Exception:
        return None


def _read_all_new_messages_from_them(page):
    """
    Read ALL messages from the other person in the currently open thread.
    Works on both mobile and desktop Instagram DOM.
    Returns list of strings (all their messages in order), or empty list.
    """
    return page.evaluate(r"""
        () => {
            const result = [];
            const skipTexts = new Set(['Seen', 'Delivered', 'Sent', 'Photo', 'Video',
                'Active now', 'Active today', 'Like', 'Liked a message', 'Translate',
                'Translated from', 'Audio', 'Voice message']);

            // Method 1: div[role="group"] with profile pic (mobile pattern)
            const groups = document.querySelectorAll('div[role="group"]');
            if (groups.length > 0) {
                for (const g of groups) {
                    const hasPic = g.querySelector('a[href] img[alt="user-profile-picture"]');
                    if (!hasPic) continue;

                    const textEls = g.querySelectorAll('span[dir="auto"], div[dir="auto"]');
                    const textsFound = [];
                    for (const el of textEls) {
                        const t = el.textContent?.trim();
                        if (t && t.length > 0 && t.length < 2000
                            && !t.match(/^\d{1,2}:\d{2}/)
                            && !skipTexts.has(t)) {
                            let isDuplicate = false;
                            for (const prev of textsFound) {
                                if (prev.includes(t) || t.includes(prev)) {
                                    isDuplicate = true;
                                    break;
                                }
                            }
                            if (!isDuplicate) textsFound.push(t);
                        }
                    }
                    for (const t of textsFound) result.push(t);
                }
                if (result.length > 0) return result;
            }

            // Method 2: Desktop pattern — div[role="row"] contains message rows
            // Each row has message bubbles; "their" messages are on the left side
            const rows = document.querySelectorAll('div[role="row"]');
            if (rows.length > 0) {
                for (const row of rows) {
                    // Their messages have a profile pic or are left-aligned
                    const hasPic = row.querySelector('img[alt="user-profile-picture"]');
                    const spans = row.querySelectorAll('span[dir="auto"], div[dir="auto"]');

                    // If row has profile pic, it's from them
                    if (hasPic) {
                        for (const el of spans) {
                            const t = el.textContent?.trim();
                            if (t && t.length > 0 && t.length < 2000
                                && !t.match(/^\d{1,2}:\d{2}/)
                                && !skipTexts.has(t)
                                && el.children.length === 0) {
                                if (!result.includes(t)) result.push(t);
                            }
                        }
                    }
                }
                if (result.length > 0) return result;
            }

            // Method 3: Fallback — find the chat container and look for message bubbles
            // On desktop, their messages are typically positioned on the left
            const chatContainer = document.querySelector('div[role="grid"]')
                || document.querySelector('section main div[style*="flex"]');
            if (chatContainer) {
                const allSpans = chatContainer.querySelectorAll('span[dir="auto"]');
                const viewW = window.innerWidth;

                for (const el of allSpans) {
                    const t = el.textContent?.trim();
                    if (!t || t.length === 0 || t.length > 2000) continue;
                    if (skipTexts.has(t)) continue;
                    if (t.match(/^\d{1,2}:\d{2}/)) continue;
                    if (el.children.length > 0) continue;

                    // Check position — their messages are on the left half
                    const rect = el.getBoundingClientRect();
                    if (rect.left < viewW * 0.4 && rect.top > 80) {
                        if (!result.includes(t)) result.push(t);
                    }
                }
            }

            return result;
        }
    """)


def _go_back_to_inbox(page):
    """Go back to inbox from a thread. On desktop, inbox list is always visible (no back needed)."""
    # On desktop, the inbox list is a side panel — we just need to be on /direct/inbox/
    if "/direct/inbox" in page.url:
        # Already in inbox view (desktop shows both list + thread)
        return

    # Try back button (mobile)
    clicked = page.evaluate("""
        () => {
            const svg = document.querySelector('svg[aria-label="Back"]');
            if (svg) {
                let el = svg;
                for (let i = 0; i < 5; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    if (el.getAttribute('role') === 'button' || el.tagName === 'BUTTON') {
                        el.click();
                        return true;
                    }
                }
                svg.parentElement.click();
                return true;
            }
            return false;
        }
    """)
    if clicked:
        human_delay(1, 2)
        return
    # Last resort: navigate (causes reload)
    page.goto(DM_INBOX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    human_delay(2, 3)


def run_loop(max_accounts=1, interval=15, headless=False):
    reset_daily_dm_counts()
    model = init_gemini()

    accounts_info = get_all_dm_accounts()[:max_accounts]
    all_accounts = {a["username"]: a for a in get_all_accounts() if a.get("role") != "scraper"}

    if not accounts_info:
        print("No DM accounts found!")
        return

    info = accounts_info[0]
    username = info["username"]
    account = all_accounts.get(username)

    if not account:
        print(f"Account @{username} not found!")
        return

    print(f"\n{'='*60}")
    print(f"DM BOT — @{username}")
    print(f"Watching inbox every {interval}s | Ctrl+C to stop")
    print(f"{'='*60}\n")

    session = open_session(account, headless=headless)

    try:
        if not ensure_logged_in(session):
            print("Login failed!")
            return

        page = session.page

        # Detect follow-backs and create pending conversations for them
        print(f"  [followback] Checking for follow-backs...")
        try:
            from dm.followback import detect_followbacks
            followbacks = detect_followbacks(page, username, max_checks=20)
            if followbacks:
                print(f"  [followback] Found {len(followbacks)} new follow-backs!")
            else:
                print(f"  [followback] No new follow-backs")
        except Exception as e:
            print(f"  [followback] Error: {e}")

        # Send openers to pending conversations (follow-backs get DMed first)
        pending = get_pending_conversations(username)
        if pending:
            # Sort by target_score descending so highest-value leads go first
            pending.sort(key=lambda c: c.get("target_score") or 0, reverse=True)
            print(f"  [opener] {len(pending)} pending conversations to open")

        for conv in pending:
            target = conv["target_username"]
            conv_id = conv["id"]
            print(f"  [opener] Sending to @{target}...")
            try:
                target_profile = get_target_profile(target)
                if not target_profile.get("username"):
                    target_profile["username"] = target
                opener = generate_opener(model, target_profile)
                if opener and send_dm(page, target, opener):
                    log_message(conv_id, username, target, "outbound", opener)
                    update_conversation(conv_id, stage="opened", last_message_by="us")
                    record_dm_sent(username)
                    print(f"  [opener] Sent: {opener[:60]}")
                else:
                    print(f"  [opener] Failed")
            except Exception as e:
                print(f"  [opener] Error: {e}")
            human_delay(5, 15)

        # Now sit in inbox and watch
        _go_to_inbox(page)
        print(f"\n  Sitting in inbox, watching for messages...\n")

        cycle = 0
        while True:
            cycle += 1
            now = datetime.now().strftime('%H:%M:%S')

            # Make sure we're in inbox (WebSocket keeps it live, no reload needed)
            if "/direct/inbox" not in page.url:
                _go_to_inbox(page)

            # Check for unread threads
            unread = _detect_unread_threads(page)

            if unread:
                names = [u["display_name"] for u in unread]
                print(f"  [{now}] Unread from: {', '.join(names)}")

                for thread_info in unread:
                  try:
                    display_name = thread_info["display_name"]
                    thread_idx = thread_info["index"]

                    # Click into the thread to get the actual username
                    if not _click_thread_by_index(page, thread_idx):
                        print(f"  [{now}] Could not open thread with {display_name}")
                        _go_to_inbox(page)
                        continue

                    # Extract the actual username from the chat header
                    target = _extract_username_from_thread(page)
                    if not target:
                        # Fallback: resolve username from display name via Supabase
                        print(f"  [{now}] DOM extraction failed for '{display_name}', trying DB lookup...")
                        target = _resolve_username_from_display_name(display_name, username)
                    if not target:
                        print(f"  [{now}] Could not resolve username for '{display_name}'")
                        _go_back_to_inbox(page)
                        continue
                    print(f"  [{now}] Resolved: '{display_name}' → @{target}")

                    # Check if we have a conversation with this person — auto-create if not
                    conv = check_existing_conversation(username, target)
                    if not conv:
                        print(f"  [{now}] @{target} is new — creating conversation")
                        conv_id = create_conversation(username, target)
                        if not conv_id:
                            print(f"  [{now}] Failed to create conversation for @{target}")
                            _go_back_to_inbox(page)
                            continue
                        update_conversation(conv_id, stage="chatting")
                    else:
                        conv_id = conv["id"]

                    # Read ALL new messages from them since our last reply
                    new_msgs = _read_all_new_messages_from_them(page)

                    if not new_msgs:
                        print(f"  [{now}] Could not read messages from @{target}")
                        _go_back_to_inbox(page)
                        continue

                    # Filter out already-logged messages
                    _, history = get_conversation_with_history(conv_id)
                    logged_inbound = set()
                    for msg in history:
                        if msg.get("direction") == "inbound":
                            logged_inbound.add(msg.get("message_text", ""))

                    truly_new = [m for m in new_msgs if m not in logged_inbound]

                    if not truly_new:
                        print(f"  [{now}] @{target}: all messages already processed")
                        _go_back_to_inbox(page)
                        continue

                    # Log ALL new messages
                    for msg_text in truly_new:
                        print(f"  [{now}] @{target} says: {msg_text[:80]}")
                        log_message(conv_id, username, target, "inbound", msg_text)
                    update_conversation(conv_id, last_message_by="them")

                    # Generate AI reply
                    print(f"  [{now}] Generating reply...")
                    _, full_history = get_conversation_with_history(conv_id)

                    # Get full conversation record and target profile for reply generation
                    from db.supabase_client import supabase
                    conv_data = supabase.table("conversations").select("*").eq("id", conv_id).single().execute().data
                    target_profile = get_target_profile(target)
                    if not target_profile.get("username"):
                        target_profile["username"] = target

                    replies, new_stage = generate_reply(model, conv_data, full_history, target_profile)
                    print(f"  [{now}] AI replies ({len(replies)}): {replies}")

                    if replies:
                        # Small human-like thinking delay before first message
                        think_time = random.uniform(5, 15)
                        print(f"  [{now}] Waiting {think_time:.0f}s before replying...")
                        time.sleep(think_time)

                        # Send each message in the reply list
                        for msg_idx, reply_text in enumerate(replies):
                            # Short pause between double/triple texts (like typing)
                            if msg_idx > 0:
                                pause = random.uniform(2, 5)
                                time.sleep(pause)

                            msg_sent = False
                            for selector in [
                                'div[role="textbox"][contenteditable="true"]',
                                'div[contenteditable="true"]',
                                'textarea[placeholder="Message..."]',
                                'textarea[placeholder*="Message"]',
                                'textarea',
                            ]:
                                try:
                                    el = page.locator(selector).first
                                    if el.is_visible(timeout=5000):
                                        el.click()
                                        human_delay(0.5, 1)
                                        page.keyboard.type(reply_text, delay=random.randint(20, 50))
                                        human_delay(0.5, 1)
                                        page.keyboard.press("Enter")
                                        msg_sent = True
                                        break
                                except Exception:
                                    continue

                            if msg_sent:
                                log_message(conv_id, username, target, "outbound", reply_text)
                                record_dm_sent(username)
                                print(f"  [{now}] Sent to @{target}: {reply_text[:60]}")
                            else:
                                print(f"  [{now}] Could not find message input to reply")
                                break

                        update_conversation(conv_id, last_message_by="us", stage=new_stage)
                    else:
                        print(f"  [{now}] AI generated empty reply")

                    human_delay(2, 3)
                    _go_back_to_inbox(page)

                  except Exception as e:
                    print(f"  [{now}] Error processing thread ({display_name}): {e}")
                    try:
                        _go_back_to_inbox(page)
                    except Exception:
                        _go_to_inbox(page)

            else:
                print(f"  [{now}] No new messages", end="\r")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nStopping DM bot...")
    finally:
        close_session(session)
        print("Browser closed.")


def main():
    parser = argparse.ArgumentParser(description="DM bot — watches inbox and replies")
    parser.add_argument("--max-accounts", type=int, default=1)
    parser.add_argument("--interval", type=int, default=15, help="Seconds between inbox checks")
    parser.add_argument("--headed", action="store_true", help="Visible browser")
    args = parser.parse_args()

    run_loop(
        max_accounts=args.max_accounts,
        interval=args.interval,
        headless=not args.headed,
    )


if __name__ == "__main__":
    main()
