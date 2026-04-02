"""
Unified daily bot — runs the full routine for all accounts in a loop.

For each account:
  1. Follow new targets (ramp-limited)
  2. Check follow-backs (who followed us back but hasn't been DMed)
  3. Send openers to pending conversations (follow-backs first)
  4. Sit in inbox watching for replies and respond with AI

Usage:
    python run_bot.py                     # all accounts, headless
    python run_bot.py --headed            # visible browser
    python run_bot.py --max-accounts 1    # only first account
    python run_bot.py --skip-follows      # skip follow phase
    python run_bot.py --inbox-time 300    # watch inbox for 5 min per account (default 10 min)
"""

import argparse
import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone

from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.browser_dm import send_dm
from core.browser_follow import follow_user
from core.utils import human_delay
from csv_management.username_manager import UsernameTracker
from dm.storage import (
    get_pending_conversations, get_conversation_with_history,
    log_message, update_conversation, check_existing_conversation,
    create_conversation, get_target_profile,
)
from dm.conversation import init_gemini, generate_opener, generate_reply
from dm.ramp import get_all_dm_accounts, record_dm_sent, reset_daily_dm_counts
from dm.followback import detect_followbacks
from follow.ramp import (
    get_all_active_accounts as get_all_follow_accounts,
    record_follow, reset_daily_counts as reset_follow_counts,
)


DM_INBOX_URL = "https://www.instagram.com/direct/inbox/"
NAV_TIMEOUT = 30000


# ── Helper functions (reused from run_dm_loop.py) ───────────

def _go_to_inbox(page):
    if "/direct/inbox" not in page.url:
        page.goto(DM_INBOX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)


def _detect_unread_threads(page):
    return page.evaluate(r"""
        () => {
            const threads = [];
            const buttons = document.querySelectorAll('div[role="button"]');
            let idx = 0;
            for (const btn of buttons) {
                const pic = btn.querySelector('img[alt="user-profile-picture"], img[draggable="false"]');
                if (!pic) continue;
                const allDivs = btn.querySelectorAll('div');
                let isUnread = false;
                for (const d of allDivs) {
                    const style = window.getComputedStyle(d);
                    if (d.offsetWidth >= 6 && d.offsetWidth <= 12
                        && d.offsetHeight >= 6 && d.offsetHeight <= 12
                        && style.borderRadius
                        && style.backgroundColor
                        && style.backgroundColor !== 'rgba(0, 0, 0, 0)') {
                        const hidden = d.querySelector('div[style*="display: none"], div[style*="visibility: hidden"]');
                        if (hidden && hidden.textContent?.includes('Unread')) {
                            isUnread = true;
                            break;
                        }
                    }
                }
                if (isUnread) {
                    const nameEl = btn.querySelector('span[dir="auto"]');
                    const name = nameEl ? nameEl.textContent.trim() : 'Unknown';
                    threads.push({ display_name: name, index: idx });
                }
                idx++;
            }
            return threads;
        }
    """)


def _click_thread_by_index(page, thread_index):
    clicked = page.evaluate(r"""
        (idx) => {
            const buttons = document.querySelectorAll('div[role="button"]');
            let count = 0;
            for (const btn of buttons) {
                const pic = btn.querySelector('img[alt="user-profile-picture"], img[draggable="false"]');
                if (!pic) continue;
                if (count === idx) { btn.click(); return true; }
                count++;
            }
            return false;
        }
    """, thread_index)
    if clicked:
        human_delay(2, 3)
    return clicked


def _extract_username_from_thread(page):
    return page.evaluate(r"""
        () => {
            const links = document.querySelectorAll('a[aria-label]');
            for (const a of links) {
                const label = a.getAttribute('aria-label') || '';
                const m = label.match(/Open the profile page of (.+)/);
                if (m) return m[1];
            }
            return null;
        }
    """)


def _read_all_new_messages_from_them(page):
    return page.evaluate(r"""
        () => {
            const result = [];
            const groups = document.querySelectorAll('div[role="group"]');
            for (const g of groups) {
                const hasPic = g.querySelector('a[href] img[alt="user-profile-picture"]');
                if (!hasPic) continue;
                const textEls = g.querySelectorAll('span[dir="auto"], div[dir="auto"]');
                const textsFound = [];
                for (const el of textEls) {
                    const t = el.textContent?.trim();
                    if (t && t.length > 0
                        && !t.match(/^\d{1,2}:\d{2}/)
                        && t !== 'Seen' && t !== 'Delivered'
                        && t !== 'Photo' && t !== 'Video'
                        && !textsFound.includes(t)) {
                        let isDuplicate = false;
                        for (const prev of textsFound) {
                            if (prev.includes(t) || t.includes(prev)) { isDuplicate = true; break; }
                        }
                        if (!isDuplicate) textsFound.push(t);
                    }
                }
                if (textsFound.length > 0) {
                    for (const t of textsFound) result.push(t);
                } else {
                    let mediaText = '';
                    const imgs = g.querySelectorAll('img');
                    for (const img of imgs) {
                        const alt = img.getAttribute('alt') || '';
                        if (alt !== 'user-profile-picture' && img.width > 50) { mediaText = '[photo]'; break; }
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
    clicked = page.evaluate("""
        () => {
            const svg = document.querySelector('svg[aria-label="Back"]');
            if (svg) {
                let el = svg;
                for (let i = 0; i < 5; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    if (el.getAttribute('role') === 'button') { el.click(); return true; }
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
    page.goto(DM_INBOX_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
    human_delay(2, 3)


def _send_message_in_thread(page, text):
    """Type and send a message in the currently open thread."""
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
                page.keyboard.type(text, delay=random.randint(20, 50))
                human_delay(0.5, 1)
                page.keyboard.press("Enter")
                return True
        except Exception:
            continue
    return False


# ── Phase 1: Follow targets ─────────────────────────────────

def phase_follow(page, username, follow_accounts_info):
    """Follow new targets based on ramp allowance."""
    ramp = follow_accounts_info.get(username)
    if not ramp:
        print(f"  [follow] @{username} not in follow ramp, skipping")
        return 0

    allowance = ramp["remaining"]
    if allowance <= 0:
        print(f"  [follow] @{username} already at daily limit ({ramp['daily_limit']})")
        return 0

    tracker = UsernameTracker()
    unused = tracker.get_unused_usernames()
    targets = unused[:allowance]

    if not targets:
        print(f"  [follow] No unused targets available")
        return 0

    print(f"  [follow] Following {len(targets)} targets (phase {ramp['phase']}, limit {ramp['daily_limit']}/day)...")
    followed = 0

    for target in targets:
        try:
            if follow_user(page, target):
                followed += 1
                record_follow(username, target)
                tracker.mark_as_used(target, followed_by=username)
                print(f"  [follow] + @{target}")
            else:
                print(f"  [follow] - @{target} (failed)")
        except Exception as e:
            err = str(e).lower()
            if "challenge" in err or "rate" in err or "limit" in err:
                print(f"  [follow] Rate limit / challenge! Stopping follows.")
                break
            print(f"  [follow] Error: {e}")

        if target != targets[-1]:
            time.sleep(random.uniform(30, 90))

    print(f"  [follow] Done: {followed}/{len(targets)} followed")
    return followed


# ── Phase 2: Check follow-backs ──────────────────────────────

def phase_followbacks(page, username):
    """Check who followed us back and create pending conversations."""
    print(f"  [followback] Checking for follow-backs...")
    try:
        followbacks = detect_followbacks(page, username, max_checks=30)
        if followbacks:
            print(f"  [followback] {len(followbacks)} new follow-backs!")
        else:
            print(f"  [followback] No new follow-backs")
        return len(followbacks)
    except Exception as e:
        print(f"  [followback] Error: {e}")
        return 0


# ── Phase 3: Send openers ───────────────────────────────────

def phase_openers(page, username, model):
    """Send openers to pending conversations (follow-backs get priority)."""
    pending = get_pending_conversations(username)
    if not pending:
        print(f"  [opener] No pending conversations")
        return 0

    # Sort by score so best leads go first
    pending.sort(key=lambda c: c.get("target_score") or 0, reverse=True)
    print(f"  [opener] {len(pending)} pending conversations to open")

    sent = 0
    for conv in pending:
        target = conv["target_username"]
        conv_id = conv["id"]

        try:
            target_profile = get_target_profile(target)
            if not target_profile.get("username"):
                target_profile["username"] = target

            opener = generate_opener(model, target_profile)
            if opener and send_dm(page, target, opener):
                log_message(conv_id, username, target, "outbound", opener)
                update_conversation(conv_id, stage="opened", last_message_by="us")
                record_dm_sent(username)
                sent += 1
                print(f"  [opener] @{target}: {opener[:60]}")
            else:
                print(f"  [opener] @{target}: failed to send")
        except Exception as e:
            print(f"  [opener] @{target}: error — {e}")

        human_delay(5, 15)

    print(f"  [opener] Done: {sent}/{len(pending)} openers sent")
    return sent


# ── Phase 4: Watch inbox and reply ───────────────────────────

def phase_inbox(page, username, model, watch_seconds=600):
    """
    Sit in inbox and watch for new messages for `watch_seconds`.
    Reply to any unread threads with AI.
    """
    _go_to_inbox(page)
    print(f"  [inbox] Watching inbox for {watch_seconds // 60} min...")

    start = time.time()
    replies_sent = 0
    check_interval = 10  # check every 10 seconds

    while time.time() - start < watch_seconds:
        now = datetime.now().strftime('%H:%M:%S')

        if "/direct/inbox" not in page.url:
            _go_to_inbox(page)

        unread = _detect_unread_threads(page)

        if unread:
            names = [u["display_name"] for u in unread]
            print(f"  [{now}] Unread from: {', '.join(names)}")

            for thread_info in unread:
                try:
                    display_name = thread_info["display_name"]
                    thread_idx = thread_info["index"]

                    if not _click_thread_by_index(page, thread_idx):
                        print(f"  [{now}] Could not open thread ({display_name})")
                        _go_to_inbox(page)
                        continue

                    target = _extract_username_from_thread(page)
                    if not target:
                        print(f"  [{now}] Could not get username ({display_name})")
                        _go_back_to_inbox(page)
                        continue

                    # Auto-create conversation if new
                    conv = check_existing_conversation(username, target)
                    if not conv:
                        print(f"  [{now}] @{target} is new — creating conversation")
                        conv_id = create_conversation(username, target)
                        if not conv_id:
                            _go_back_to_inbox(page)
                            continue
                        update_conversation(conv_id, stage="chatting")
                    else:
                        conv_id = conv["id"]

                    # Read all new messages from them
                    new_msgs = _read_all_new_messages_from_them(page)
                    if not new_msgs:
                        print(f"  [{now}] @{target}: no readable messages")
                        _go_back_to_inbox(page)
                        continue

                    # Filter already-logged messages
                    _, full_history = get_conversation_with_history(conv_id)
                    logged = set()
                    for m in full_history:
                        if m.get("direction") == "inbound":
                            logged.add(m.get("message_text", ""))

                    truly_new = [m for m in new_msgs if m not in logged]
                    if not truly_new:
                        _go_back_to_inbox(page)
                        continue

                    # Log new messages
                    for msg_text in truly_new:
                        print(f"  [{now}] @{target} says: {msg_text[:80]}")
                        log_message(conv_id, username, target, "inbound", msg_text)
                    update_conversation(conv_id, last_message_by="them")

                    # Generate AI reply
                    _, full_history = get_conversation_with_history(conv_id)

                    from db.supabase_client import supabase
                    conv_data = supabase.table("conversations").select("*").eq("id", conv_id).single().execute().data
                    target_profile = get_target_profile(target)
                    if not target_profile.get("username"):
                        target_profile["username"] = target

                    replies, new_stage = generate_reply(model, conv_data, full_history, target_profile)
                    print(f"  [{now}] AI replies ({len(replies)}): {replies}")

                    if replies:
                        think_time = random.uniform(5, 15)
                        print(f"  [{now}] Waiting {think_time:.0f}s before replying...")
                        time.sleep(think_time)

                        for msg_idx, reply_text in enumerate(replies):
                            if msg_idx > 0:
                                time.sleep(random.uniform(2, 5))

                            if _send_message_in_thread(page, reply_text):
                                log_message(conv_id, username, target, "outbound", reply_text)
                                record_dm_sent(username)
                                print(f"  [{now}] Sent to @{target}: {reply_text[:60]}")
                            else:
                                print(f"  [{now}] Could not send message")
                                break

                        update_conversation(conv_id, last_message_by="us", stage=new_stage)
                        replies_sent += 1

                    human_delay(2, 3)
                    _go_back_to_inbox(page)

                except Exception as e:
                    print(f"  [{now}] Error ({display_name}): {e}")
                    try:
                        _go_back_to_inbox(page)
                    except Exception:
                        _go_to_inbox(page)
        else:
            elapsed = int(time.time() - start)
            remaining = watch_seconds - elapsed
            print(f"  [{now}] No new messages ({remaining}s remaining)", end="\r")

        time.sleep(check_interval)

    print(f"\n  [inbox] Done: {replies_sent} replies sent")
    return replies_sent


# ── Main orchestrator ────────────────────────────────────────

def run_bot(max_accounts=None, headless=True, skip_follows=False, inbox_time=600):
    """
    Run the full daily routine for all accounts.

    Per account:
      1. Follow targets (ramp-limited)
      2. Check follow-backs
      3. Send openers to pending conversations
      4. Watch inbox for replies (inbox_time seconds)

    Then cycle to next account. After all accounts done, start over.
    """
    reset_follow_counts()
    reset_daily_dm_counts()
    model = init_gemini()

    all_accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]
    if max_accounts:
        all_accounts = all_accounts[:max_accounts]

    if not all_accounts:
        print("No accounts found!")
        return

    # Get follow ramp info
    follow_ramp = {a["username"]: a for a in get_all_follow_accounts()}

    print(f"\n{'='*60}")
    print(f"UNIFIED BOT — {len(all_accounts)} accounts")
    print(f"Skip follows: {skip_follows}")
    print(f"Inbox watch time: {inbox_time // 60} min per account")
    print(f"Ctrl+C to stop")
    print(f"{'='*60}")
    for acc in all_accounts:
        u = acc.get("username", "???")
        ramp = follow_ramp.get(u, {})
        print(f"  @{u}: follow phase {ramp.get('phase', '?')}, "
              f"limit {ramp.get('daily_limit', '?')}/day, "
              f"remaining {ramp.get('remaining', '?')}")
    print(f"{'='*60}\n")

    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"\n{'#'*60}")
            print(f"CYCLE {cycle} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'#'*60}")

            for i, account in enumerate(all_accounts):
                username = account.get("username", "???")
                print(f"\n{'='*50}")
                print(f"Account {i+1}/{len(all_accounts)}: @{username}")
                print(f"{'='*50}")

                session = None
                try:
                    session = open_session(account, headless=headless)

                    if not ensure_logged_in(session):
                        print(f"  Login failed for @{username}, skipping")
                        continue

                    page = session.page

                    # Phase 1: Follow targets
                    if not skip_follows:
                        phase_follow(page, username, follow_ramp)
                        human_delay(5, 10)

                    # Phase 2: Check follow-backs
                    phase_followbacks(page, username)
                    human_delay(3, 5)

                    # Phase 3: Send openers
                    phase_openers(page, username, model)
                    human_delay(3, 5)

                    # Phase 4: Watch inbox
                    phase_inbox(page, username, model, watch_seconds=inbox_time)

                except Exception as e:
                    print(f"  Error for @{username}: {e}")

                finally:
                    if session:
                        close_session(session)

                # Wait between accounts
                if i < len(all_accounts) - 1:
                    wait = random.uniform(30, 60)
                    print(f"\n  Waiting {wait:.0f}s before next account...")
                    time.sleep(wait)

            # After all accounts, refresh follow ramp for next cycle
            follow_ramp = {a["username"]: a for a in get_all_follow_accounts()}

            # Short break between cycles
            print(f"\n  Cycle {cycle} complete. Starting next cycle in 60s...")
            time.sleep(60)

    except KeyboardInterrupt:
        print("\n\nBot stopped.")


def main():
    parser = argparse.ArgumentParser(description="Unified daily bot — follow + DM + inbox for all accounts")
    parser.add_argument("--max-accounts", type=int, default=None, help="Limit accounts to process")
    parser.add_argument("--headed", action="store_true", help="Visible browser")
    parser.add_argument("--skip-follows", action="store_true", help="Skip the follow phase")
    parser.add_argument("--inbox-time", type=int, default=600, help="Seconds to watch inbox per account (default: 600 = 10 min)")
    args = parser.parse_args()

    run_bot(
        max_accounts=args.max_accounts,
        headless=not args.headed,
        skip_follows=args.skip_follows,
        inbox_time=args.inbox_time,
    )


if __name__ == "__main__":
    main()
