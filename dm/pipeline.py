"""
DM pipeline — main daily orchestrator using Playwright browser sessions.

Flow per account:
1. Phase A: Check follow-backs (visit profiles)
2. Phase B: Send openers to pending conversations
3. Phase D: Check inbox for new replies
4. Phase C: Reply to active conversations with AI
5. Phase E: Follow up on unresponsive targets (3 attempts max)
"""

import random
import time

from datetime import datetime, timezone, timedelta

from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from config import (
    DM_BETWEEN_THREADS_SEC,
    DM_COLD_AFTER_HOURS,
    DM_MAX_COLD_ATTEMPTS,
    DM_FOLLOWUP_1_AFTER_HOURS,
    DM_FOLLOWUP_2_AFTER_HOURS,
    DM_ACTIVE_HOURS,
)
from dm.ramp import (
    reset_daily_dm_counts,
    get_all_dm_accounts,
    record_dm_sent,
)
from dm.storage import (
    get_pending_conversations,
    get_active_conversations,
    get_conversations_needing_reply,
    get_conversations_needing_followup,
    get_conversation_with_history,
    get_target_profile,
    log_message,
    update_conversation,
    increment_attempts,
    get_conversation_stats,
)
from dm.followback import detect_followbacks
from dm.inbox import send_dm, get_last_message_from_them, get_unread_threads, get_our_username
from dm.conversation import (
    init_gemini,
    generate_opener,
    generate_reply,
    generate_followup,
    classify_reply,
    calculate_reply_delay,
    should_mark_dead,
)


def _is_active_hours():
    """Check if current time is within DM sending hours."""
    current_hour = datetime.now().hour
    start, end = DM_ACTIVE_HOURS
    return start <= current_hour < end


def phase_a_detect_followbacks(page, account_username):
    """Phase A: Check for new follow-backs via browser."""
    print(f"\n  [Phase A] Detecting follow-backs for @{account_username}...")
    followbacks = detect_followbacks(page, account_username, max_checks=30)
    print(f"  [Phase A] Found {len(followbacks)} new follow-backs")
    return len(followbacks)


def phase_b_send_openers(page, account_username, model, dm_budget):
    """Phase B: Send openers to pending conversations."""
    print(f"\n  [Phase B] Sending openers (budget: {dm_budget})...")

    pending = get_pending_conversations(account_username)
    if not pending:
        print("  [Phase B] No pending conversations")
        return 0

    # Hot leads first
    pending.sort(key=lambda c: c.get("target_score") or 0, reverse=True)

    sent = 0

    for conv in pending[:dm_budget]:
        target = conv["target_username"]
        conv_id = conv["id"]

        print(f"\n  [Phase B] Opening DM with @{target} (score: {conv.get('target_score', '?')})...")

        profile = get_target_profile(target)
        opener = generate_opener(model, profile)
        print(f"  [Phase B] Opener: {opener[:80]}...")

        if send_dm(page, target, opener):
            now = datetime.now(timezone.utc).isoformat()
            log_message(conv_id, account_username, target, "outbound", opener)
            update_conversation(conv_id,
                stage="opened",
                opened_at=now,
                last_message_at=now,
                last_message_by="us",
                opener_type="ai_personalized" if profile.get("bio") else "ai_generic",
                attempts=1,
            )
            record_dm_sent(account_username)
            sent += 1
            print(f"  [Phase B] Opener sent to @{target}")
        else:
            print(f"  [Phase B] Failed to send to @{target}")

        if sent < dm_budget:
            wait = random.randint(*DM_BETWEEN_THREADS_SEC)
            print(f"  [Phase B] Waiting {wait}s...")
            time.sleep(wait)

    print(f"  [Phase B] Sent {sent} openers")
    return sent


def phase_c_handle_replies(page, account_username, model, dm_budget):
    """Phase C: Reply to active conversations."""
    print(f"\n  [Phase C] Handling replies (budget: {dm_budget})...")

    needing_reply = get_conversations_needing_reply(account_username)

    if not needing_reply:
        print("  [Phase C] No conversations need replies right now")
        return 0

    sent = 0

    for conv in needing_reply[:dm_budget]:
        conv_id = conv["id"]
        target = conv["target_username"]
        messages_sent = conv.get("messages_sent", 0)

        print(f"\n  [Phase C] Replying to @{target} (msg #{messages_sent + 1})...")

        if should_mark_dead(conv):
            update_conversation(conv_id, stage="dead", outcome="dead")
            print(f"  [Phase C] Marked @{target} as dead (hit message limit)")
            continue

        _, history = get_conversation_with_history(conv_id)
        profile = get_target_profile(target)

        # Get their last message for classification
        last_their_msg = None
        for msg in reversed(history):
            if msg.get("direction") == "inbound":
                last_their_msg = msg.get("message_text", "")
                break

        reply_class = None
        if last_their_msg:
            reply_class = classify_reply(model, last_their_msg)
            print(f"  [Phase C] Reply classified as: {reply_class}")

            if reply_class in ("not_interested", "hostile"):
                update_conversation(conv_id, stage="dead", outcome="dead")
                print(f"  [Phase C] Marked @{target} as dead ({reply_class})")
                continue

        reply, current_stage = generate_reply(model, conv, history, profile)
        print(f"  [Phase C] Reply: {reply[:80]}... (stage: {current_stage})")

        if send_dm(page, target, reply):
            now = datetime.now(timezone.utc).isoformat()
            log_message(conv_id, account_username, target, "outbound", reply)

            updates = {"last_message_at": now, "last_message_by": "us", "stage": current_stage}
            if current_stage in ("5_SOFT_PITCH", "6_LINK_DELIVERY") and not conv.get("pitched_at"):
                updates["pitched_at"] = now
                updates["pitch_message_number"] = messages_sent + 1

            update_conversation(conv_id, **updates)
            record_dm_sent(account_username)
            sent += 1
            print(f"  [Phase C] Reply sent to @{target} (stage: {current_stage})")
        else:
            print(f"  [Phase C] Failed to reply to @{target}")

        if sent < dm_budget:
            wait = random.randint(*DM_BETWEEN_THREADS_SEC)
            print(f"  [Phase C] Waiting {wait}s...")
            time.sleep(wait)

    print(f"  [Phase C] Sent {sent} replies")
    return sent


def phase_d_check_inbox_for_new_replies(page, account_username):
    """Phase D: Scan inbox for new messages and log them."""
    print(f"\n  [Phase D] Scanning inbox for new replies...")

    active_convos = get_active_conversations(account_username)

    if not active_convos:
        print("  [Phase D] No active conversations to check")
        return 0

    new_replies = 0

    for conv in active_convos:
        if conv.get("last_message_by") != "us":
            continue

        target = conv["target_username"]
        conv_id = conv["id"]

        try:
            last_msg = get_last_message_from_them(page, target)

            if last_msg:
                _, history = get_conversation_with_history(conv_id)
                last_logged_inbound = None
                for msg in reversed(history):
                    if msg.get("direction") == "inbound":
                        last_logged_inbound = msg.get("message_text", "")
                        break

                if last_msg != last_logged_inbound:
                    print(f"  [Phase D] New reply from @{target}: {last_msg[:60]}...")
                    log_message(conv_id, account_username, target, "inbound", last_msg)

                    # Classify to determine delay
                    from dm.conversation import classify_reply as _classify
                    reply_class = _classify(init_gemini(), last_msg)

                    delay = calculate_reply_delay(conv, last_msg, reply_classification=reply_class)
                    reply_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()

                    update_conversation(conv_id,
                        last_message_by="them",
                        next_reply_at=reply_at,
                    )

                    delay_min = delay // 60
                    print(f"  [Phase D] Scheduled reply in {delay_min} min (class: {reply_class})")
                    new_replies += 1

            time.sleep(random.uniform(1, 3))

        except Exception as e:
            print(f"  [Phase D] Error checking @{target}: {e}")

    print(f"  [Phase D] Detected {new_replies} new replies")
    return new_replies


def phase_e_send_followups(page, account_username, model, dm_budget):
    """
    Phase E: Follow up on unresponsive targets.
    3 attempts max: opener -> 48h -> follow-up #1 -> 24h -> follow-up #2 -> dead
    """
    print(f"\n  [Phase E] Checking for follow-up opportunities (budget: {dm_budget})...")

    followup_1 = get_conversations_needing_followup(account_username, DM_FOLLOWUP_1_AFTER_HOURS)
    followup_2 = get_conversations_needing_followup(account_username, DM_FOLLOWUP_2_AFTER_HOURS)

    needs_followup = []
    seen_ids = set()

    for conv in followup_1 + followup_2:
        if conv["id"] in seen_ids:
            continue
        seen_ids.add(conv["id"])
        attempts = conv.get("attempts") or 1
        if attempts < DM_MAX_COLD_ATTEMPTS:
            needs_followup.append(conv)

    if not needs_followup:
        print("  [Phase E] No follow-ups needed")
        return 0

    sent = 0

    for conv in needs_followup[:dm_budget]:
        conv_id = conv["id"]
        target = conv["target_username"]
        attempts = conv.get("attempts") or 1

        attempt_number = attempts + 1

        if attempt_number > DM_MAX_COLD_ATTEMPTS:
            update_conversation(conv_id, stage="dead", outcome="dead")
            print(f"  [Phase E] @{target} marked dead (max attempts reached)")
            continue

        print(f"\n  [Phase E] Follow-up #{attempt_number} to @{target}...")

        _, history = get_conversation_with_history(conv_id)
        followup = generate_followup(model, conv, history, attempt_number)
        print(f"  [Phase E] Follow-up: {followup[:80]}...")

        if send_dm(page, target, followup):
            now = datetime.now(timezone.utc).isoformat()
            log_message(conv_id, account_username, target, "outbound", followup)
            increment_attempts(conv_id)
            update_conversation(conv_id, last_message_at=now, last_message_by="us")
            record_dm_sent(account_username)
            sent += 1
            print(f"  [Phase E] Follow-up #{attempt_number} sent to @{target}")

            if attempt_number >= DM_MAX_COLD_ATTEMPTS:
                update_conversation(conv_id, stage="dead", outcome="dead")
                print(f"  [Phase E] @{target} marked dead (final attempt sent)")
        else:
            print(f"  [Phase E] Failed to send follow-up to @{target}")

        if sent < dm_budget:
            wait = random.randint(*DM_BETWEEN_THREADS_SEC)
            time.sleep(wait)

    print(f"  [Phase E] Sent {sent} follow-ups")
    return sent


def run_dm_pipeline(max_accounts=None, dry_run=False, **kwargs):
    """
    Main entry point — run the full DM pipeline for all accounts via browser.
    """
    if not _is_active_hours():
        h_start, h_end = DM_ACTIVE_HOURS
        print(f"Outside active hours ({h_start}:00-{h_end}:00). Skipping DM run.")
        return {"accounts": 0, "followbacks": 0, "openers_sent": 0, "replies_sent": 0, "followups_sent": 0, "errors": 0}

    reset_daily_dm_counts()
    model = init_gemini()

    accounts_info = get_all_dm_accounts()
    if max_accounts:
        accounts_info = accounts_info[:max_accounts]

    all_accounts = {a["username"]: a for a in get_all_accounts() if a.get("role") != "scraper"}

    print(f"\n{'='*60}")
    print(f"DM PIPELINE RUN (BROWSER-BASED)")
    print(f"Accounts: {len(accounts_info)}")
    print(f"Dry run: {dry_run}")
    print(f"Active hours: {DM_ACTIVE_HOURS[0]}:00-{DM_ACTIVE_HOURS[1]}:00")
    print(f"Max cold attempts: {DM_MAX_COLD_ATTEMPTS}")
    print(f"{'='*60}")
    for info in accounts_info:
        print(f"  @{info['username']}: Week {info['dm_week']} | "
              f"Limit {info['dm_daily_limit']}/day | "
              f"Done: {info['daily_dms_sent']} | "
              f"Remaining: {info['dm_remaining']} | "
              f"Total DMs: {info['total_dms_sent']}")
    print(f"{'='*60}\n")

    total_openers = 0
    total_replies = 0
    total_followbacks = 0
    total_followups = 0
    errors = 0

    for i, info in enumerate(accounts_info):
        username = info["username"]
        dm_remaining = info["dm_remaining"]

        if dm_remaining <= 0:
            print(f"\n--- Account {i+1}/{len(accounts_info)}: @{username} ---")
            print(f"    Already at daily DM limit, skipping")
            continue

        account = all_accounts.get(username)
        if not account:
            print(f"\n--- Account {i+1}/{len(accounts_info)}: @{username} ---")
            print(f"    Not found in accounts data, skipping")
            continue

        print(f"\n--- Account {i+1}/{len(accounts_info)}: @{username} ---")
        print(f"    Week {info['dm_week']} | Budget: {dm_remaining} DMs")

        if dry_run:
            print(f"    [DRY RUN] Would process DMs")
            continue

        session = None
        try:
            session = open_session(account, headless=True)

            if not ensure_logged_in(session):
                print(f"    Could not log in @{username}, skipping")
                errors += 1
                continue

            page = session.page

            # Phase A: Detect follow-backs
            fb = phase_a_detect_followbacks(page, username)
            total_followbacks += fb

            # Budget: 50% openers, 30% replies, 20% follow-ups
            opener_budget = max(1, int(dm_remaining * 0.5))
            reply_budget = max(1, int(dm_remaining * 0.3))
            followup_budget = dm_remaining - opener_budget - reply_budget

            # Phase B: Send openers
            openers = phase_b_send_openers(page, username, model, opener_budget)
            total_openers += openers

            # Phase D: Check inbox
            phase_d_check_inbox_for_new_replies(page, username)

            # Phase C: Reply to conversations
            remaining = dm_remaining - openers
            if remaining > 0:
                replies = phase_c_handle_replies(page, username, model, min(remaining, reply_budget))
                total_replies += replies
                remaining -= replies

            # Phase E: Follow-ups for cold targets
            if remaining > 0:
                followups = phase_e_send_followups(page, username, model, min(remaining, followup_budget))
                total_followups += followups

        except Exception as e:
            print(f"    Error for @{username}: {e}")
            errors += 1

        finally:
            if session:
                close_session(session)

        if i < len(accounts_info) - 1:
            wait = random.uniform(60, 120)
            print(f"\n    Waiting {wait:.0f}s before next account...")
            time.sleep(wait)

    stats = get_conversation_stats()

    summary = {
        "accounts": len(accounts_info),
        "followbacks": total_followbacks,
        "openers_sent": total_openers,
        "replies_sent": total_replies,
        "followups_sent": total_followups,
        "errors": errors,
        "conversations": stats,
    }

    print(f"\n{'='*60}")
    print(f"DM PIPELINE SUMMARY")
    print(f"Accounts processed: {summary['accounts']}")
    print(f"Follow-backs found: {summary['followbacks']}")
    print(f"Openers sent: {summary['openers_sent']}")
    print(f"Replies sent: {summary['replies_sent']}")
    print(f"Follow-ups sent: {summary['followups_sent']}")
    print(f"Errors: {summary['errors']}")
    if stats:
        print(f"Conversations: {stats.get('total', 0)} total | "
              f"{stats.get('opened', 0)} opened | "
              f"{stats.get('chatting', 0)} chatting | "
              f"{stats.get('pitched', 0)} pitched | "
              f"{stats.get('converted', 0)} converted | "
              f"{stats.get('dead', 0)} dead")
    print(f"{'='*60}\n")

    return summary
