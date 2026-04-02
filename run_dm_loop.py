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
    On mobile, Instagram puts a hidden <div>Unread</div> inside unread thread buttons.
    Display names are shown (not usernames), so we return the index of the unread
    thread button to click it later and extract the username from inside the chat.

    Returns list of dicts: [{"display_name": str, "index": int}]
    """
    return page.evaluate(r"""
        () => {
            const unread = [];

            // Each thread is a div[role="button"] containing an img[alt="user-profile-picture"]
            const allButtons = document.querySelectorAll('div[role="button"]');
            let threadIndex = 0;

            for (const btn of allButtons) {
                // Only consider buttons that look like thread items (have profile pic)
                const pics = btn.querySelectorAll('img[alt="user-profile-picture"]');
                if (pics.length === 0) continue;

                // Check for hidden "Unread" marker
                const divs = btn.querySelectorAll('div');
                let hasUnread = false;
                for (const d of divs) {
                    if (d.childNodes.length === 1
                        && d.childNodes[0].nodeType === 3
                        && d.textContent.trim() === 'Unread'
                        && d.offsetWidth < 2) {
                        hasUnread = true;
                        break;
                    }
                }

                if (hasUnread) {
                    // Get the display name from the first visible span
                    const spans = btn.querySelectorAll('span');
                    let displayName = '';
                    for (const s of spans) {
                        const t = s.textContent?.trim();
                        if (t && t.length > 0 && t !== 'Unread' && t !== '·'
                            && !t.startsWith('You:') && s.offsetWidth > 0) {
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
            const allButtons = document.querySelectorAll('div[role="button"]');
            let threadIndex = 0;
            for (const btn of allButtons) {
                const pics = btn.querySelectorAll('img[alt="user-profile-picture"]');
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
    On mobile, the chat header has a link like:
      <a href="/username/" aria-label="Open the profile page of username">
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
            // Look for profile links in the chat header area
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const match = href.match(/^\/([a-zA-Z0-9._]+)\/$/);
                if (match && !['direct', 'explore', 'reels', 'accounts'].includes(match[1])) {
                    return match[1];
                }
            }

            // Method 3: URL contains thread ID, check for username in page content
            const headings = document.querySelectorAll('heading, h1, h2');
            // Not reliable on mobile — display name only

            return null;
        }
    """)


def _read_all_new_messages_from_them(page):
    """
    Read ALL messages from the other person in the currently open thread.
    On mobile Instagram:
      - Their messages are inside div[role="group"] with a profile pic link
      - Our messages do NOT have div[role="group"]
      - Text is in span[dir="auto"] inside div[role="presentation"]
    Returns list of strings (all their messages in order), or empty list.
    """
    return page.evaluate(r"""
        () => {
            const result = [];

            // Find ALL div[role="group"] — each one is a message from them
            const groups = document.querySelectorAll('div[role="group"]');

            for (const g of groups) {
                // Verify it has a profile pic (confirms it's from them)
                const hasPic = g.querySelector('a[href] img[alt="user-profile-picture"]');
                if (!hasPic) continue;

                // Extract ALL text messages from this group
                // (consecutive messages from same person can be in one group)
                const textEls = g.querySelectorAll('span[dir="auto"], div[dir="auto"]');
                const textsFound = [];
                for (const el of textEls) {
                    const t = el.textContent?.trim();
                    if (t && t.length > 0
                        && !t.match(/^\d{1,2}:\d{2}/)
                        && t !== 'Seen' && t !== 'Delivered'
                        && t !== 'Photo' && t !== 'Video'
                        && !textsFound.includes(t)) {
                        // Skip if this is a child of an element we already captured
                        let isDuplicate = false;
                        for (const prev of textsFound) {
                            if (prev.includes(t) || t.includes(prev)) {
                                isDuplicate = true;
                                break;
                            }
                        }
                        if (!isDuplicate) {
                            textsFound.push(t);
                        }
                    }
                }

                if (textsFound.length > 0) {
                    for (const t of textsFound) {
                        result.push(t);
                    }
                } else {
                    // Check for media if no text found
                    let mediaText = '';
                    const imgs = g.querySelectorAll('img');
                    for (const img of imgs) {
                        const alt = img.getAttribute('alt') || '';
                        if (alt !== 'user-profile-picture' && img.width > 50) {
                            mediaText = '[photo]';
                            break;
                        }
                    }
                    if (!mediaText && g.querySelector('video')) mediaText = '[video]';
                    if (!mediaText) mediaText = '[media]';
                    result.push(mediaText);
                }
            }

            return result;
        }
    """)


def _go_back_to_inbox(page):
    """Go back to inbox from a thread using the back button (no page reload)."""
    # The back button is: svg[aria-label="Back"] inside a span, inside a div,
    # inside a div[role="button"]. Click the role="button" ancestor.
    clicked = page.evaluate("""
        () => {
            const svg = document.querySelector('svg[aria-label="Back"]');
            if (svg) {
                // Walk up to find the clickable div[role="button"]
                let el = svg;
                for (let i = 0; i < 5; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    if (el.getAttribute('role') === 'button') {
                        el.click();
                        return true;
                    }
                }
                // Fallback: click the svg's parent
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
                        print(f"  [{now}] Could not extract username from thread ({display_name})")
                        _go_back_to_inbox(page)
                        continue

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
