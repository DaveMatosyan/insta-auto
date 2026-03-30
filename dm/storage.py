"""
Supabase CRUD for DM conversations and message logs.
"""

from datetime import datetime, timezone

from db.supabase_client import supabase


# ── Conversation CRUD ────────────────────────────────────────

def create_conversation(account_username, target_username, target_score=None):
    """
    Create a new conversation record (stage=pending).

    Returns:
        int: conversation id, or None on error
    """
    try:
        row = {
            "account_username": account_username,
            "target_username": target_username,
            "stage": "pending",
            "messages_sent": 0,
            "messages_received": 0,
            "target_score": target_score,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = supabase.table("conversations").insert(row).execute()
        if resp.data:
            conv_id = resp.data[0]["id"]
            print(f"  [dm-db] Created conversation #{conv_id}: @{account_username} → @{target_username}")
            return conv_id
        return None
    except Exception as e:
        # Likely duplicate — conversation already exists
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return get_conversation_id(account_username, target_username)
        print(f"  [dm-db] Error creating conversation: {e}")
        return None


def get_conversation_id(account_username, target_username):
    """Get conversation ID for an account-target pair."""
    try:
        resp = supabase.table("conversations") \
            .select("id") \
            .eq("account_username", account_username) \
            .eq("target_username", target_username) \
            .limit(1) \
            .execute()
        if resp.data:
            return resp.data[0]["id"]
        return None
    except Exception as e:
        print(f"  [dm-db] Error getting conversation ID: {e}")
        return None


def update_conversation(conv_id, **fields):
    """Update conversation fields."""
    try:
        supabase.table("conversations") \
            .update(fields) \
            .eq("id", conv_id) \
            .execute()
    except Exception as e:
        print(f"  [dm-db] Error updating conversation #{conv_id}: {e}")


def get_conversations_by_stage(account_username, stage):
    """
    Get all conversations for an account at a specific stage.

    Returns:
        list of conversation dicts
    """
    try:
        resp = supabase.table("conversations") \
            .select("*") \
            .eq("account_username", account_username) \
            .eq("stage", stage) \
            .order("created_at") \
            .execute()
        return resp.data or []
    except Exception as e:
        print(f"  [dm-db] Error fetching {stage} conversations: {e}")
        return []


def get_pending_conversations(account_username):
    """Get conversations waiting to be opened (follow-backs not yet DMed)."""
    return get_conversations_by_stage(account_username, "pending")


def get_active_conversations(account_username):
    """Get conversations that are in progress (opened, chatting, or pitched)."""
    try:
        resp = supabase.table("conversations") \
            .select("*") \
            .eq("account_username", account_username) \
            .in_("stage", ["opened", "chatting", "pitched"]) \
            .order("last_message_at", desc=True) \
            .execute()
        return resp.data or []
    except Exception as e:
        print(f"  [dm-db] Error fetching active conversations: {e}")
        return []


def get_conversations_needing_reply(account_username):
    """
    Get conversations where the last message was from the target (they replied, we need to respond).
    Only returns conversations that are past their scheduled reply time.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        resp = supabase.table("conversations") \
            .select("*") \
            .eq("account_username", account_username) \
            .eq("last_message_by", "them") \
            .in_("stage", ["opened", "chatting", "pitched"]) \
            .lte("next_reply_at", now) \
            .order("last_message_at") \
            .execute()
        return resp.data or []
    except Exception as e:
        print(f"  [dm-db] Error fetching conversations needing reply: {e}")
        return []


def get_conversation_with_history(conv_id):
    """
    Get a conversation and its full message history.

    Returns:
        tuple: (conversation_dict, list_of_messages)
    """
    try:
        conv_resp = supabase.table("conversations") \
            .select("*") \
            .eq("id", conv_id) \
            .single() \
            .execute()

        msgs_resp = supabase.table("dm_log") \
            .select("*") \
            .eq("conversation_id", conv_id) \
            .order("sent_at") \
            .execute()

        return conv_resp.data, msgs_resp.data or []
    except Exception as e:
        print(f"  [dm-db] Error fetching conversation #{conv_id} with history: {e}")
        return None, []


# ── Message logging ──────────────────────────────────────────

def log_message(conv_id, account_username, target_username, direction, message_text):
    """
    Log a sent or received message.

    Args:
        conv_id: conversation ID
        account_username: our account
        target_username: the target
        direction: 'outbound' or 'inbound'
        message_text: the message content
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        supabase.table("dm_log").insert({
            "conversation_id": conv_id,
            "account_username": account_username,
            "target_username": target_username,
            "direction": direction,
            "message_text": message_text,
            "sent_at": now,
        }).execute()

        # Update conversation counters
        updates = {"last_message_at": now}
        if direction == "outbound":
            updates["last_message_by"] = "us"
        else:
            updates["last_message_by"] = "them"

        # Increment appropriate counter
        conv_resp = supabase.table("conversations") \
            .select("messages_sent, messages_received") \
            .eq("id", conv_id) \
            .single() \
            .execute()

        if conv_resp.data:
            if direction == "outbound":
                updates["messages_sent"] = (conv_resp.data.get("messages_sent") or 0) + 1
            else:
                updates["messages_received"] = (conv_resp.data.get("messages_received") or 0) + 1

        update_conversation(conv_id, **updates)

    except Exception as e:
        print(f"  [dm-db] Error logging message: {e}")


def get_message_history(conv_id, limit=50):
    """Get message history for a conversation."""
    try:
        resp = supabase.table("dm_log") \
            .select("*") \
            .eq("conversation_id", conv_id) \
            .order("sent_at") \
            .limit(limit) \
            .execute()
        return resp.data or []
    except Exception as e:
        print(f"  [dm-db] Error fetching messages for conversation #{conv_id}: {e}")
        return []


# ── Target lookups ───────────────────────────────────────────

def get_target_profile(target_username):
    """
    Look up a target's profile data from targets_scored table.

    Returns:
        dict with profile info, or empty dict
    """
    try:
        resp = supabase.table("targets_scored") \
            .select("*") \
            .eq("username", target_username) \
            .limit(1) \
            .execute()
        if resp.data:
            return resp.data[0]
        return {}
    except Exception as e:
        print(f"  [dm-db] Error fetching target profile @{target_username}: {e}")
        return {}


def check_existing_conversation(account_username, target_username):
    """Check if a conversation already exists between account and target."""
    try:
        resp = supabase.table("conversations") \
            .select("id, stage") \
            .eq("account_username", account_username) \
            .eq("target_username", target_username) \
            .limit(1) \
            .execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        print(f"  [dm-db] Error checking existing conversation: {e}")
        return None


# ── Analytics helpers ────────────────────────────────────────

def get_conversations_needing_followup(account_username, followup_after_hours):
    """
    Get conversations where we sent the last message and enough time has passed
    for a follow-up. Only returns conversations that haven't hit max attempts.

    Args:
        account_username: our account
        followup_after_hours: hours since last message before following up

    Returns:
        list of conversation dicts
    """
    try:
        from config import DM_MAX_COLD_ATTEMPTS
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=followup_after_hours)).isoformat()

        resp = supabase.table("conversations") \
            .select("*") \
            .eq("account_username", account_username) \
            .eq("last_message_by", "us") \
            .in_("stage", ["opened", "chatting"]) \
            .lt("last_message_at", cutoff) \
            .execute()

        # Filter by attempts < max
        results = []
        for conv in resp.data or []:
            attempts = conv.get("attempts") or 0
            if attempts < DM_MAX_COLD_ATTEMPTS:
                results.append(conv)

        return results

    except Exception as e:
        print(f"  [dm-db] Error fetching conversations needing followup: {e}")
        return []


def increment_attempts(conv_id):
    """Increment the attempts counter for a conversation."""
    try:
        resp = supabase.table("conversations") \
            .select("attempts") \
            .eq("id", conv_id) \
            .single() \
            .execute()

        current = (resp.data.get("attempts") or 0) if resp.data else 0
        update_conversation(conv_id, attempts=current + 1)
    except Exception as e:
        print(f"  [dm-db] Error incrementing attempts for #{conv_id}: {e}")


def get_conversation_stats(account_username=None):
    """Get conversation statistics, optionally filtered by account."""
    try:
        query = supabase.table("conversations").select("stage, outcome")
        if account_username:
            query = query.eq("account_username", account_username)
        resp = query.execute()

        stats = {
            "total": 0,
            "pending": 0,
            "opened": 0,
            "chatting": 0,
            "pitched": 0,
            "converted": 0,
            "cold": 0,
            "dead": 0,
        }
        for row in resp.data or []:
            stats["total"] += 1
            stage = row.get("stage", "")
            if stage in stats:
                stats[stage] += 1

        return stats
    except Exception as e:
        print(f"  [dm-db] Error getting conversation stats: {e}")
        return {}
