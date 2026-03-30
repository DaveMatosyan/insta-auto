"""
Instagram DM operations via instagrapi API.
Replaces Playwright browser automation with direct API calls.
"""

import time
import random


def send_dm(client, target_username, text):
    """
    Send a direct message to a target user.

    Args:
        client: instagrapi Client (logged in)
        target_username: who to message
        text: message content

    Returns:
        bool: True if sent successfully
    """
    try:
        user_id = client.user_id_from_username(target_username)
        client.direct_send(text, user_ids=[int(user_id)])
        print(f"  [dm] Sent to @{target_username}: {text[:60]}{'...' if len(text) > 60 else ''}")
        return True
    except Exception as e:
        print(f"  [dm] Error sending to @{target_username}: {e}")
        return False


def read_thread_messages(client, target_username, our_user_id, limit=20):
    """
    Read messages from a DM thread with a specific user.

    Args:
        client: instagrapi Client
        target_username: the other person
        our_user_id: our account's user ID (to determine message direction)
        limit: max messages to return

    Returns:
        list of dicts: [{"text": str, "from": "us"|"them", "timestamp": datetime}]
    """
    try:
        user_id = client.user_id_from_username(target_username)
        thread = client.direct_thread_by_participants([int(user_id)])

        if not thread:
            return []

        messages = client.direct_messages(thread.id, amount=limit)
        result = []

        for msg in messages:
            if not msg.text:
                continue
            direction = "us" if str(msg.user_id) == str(our_user_id) else "them"
            result.append({
                "text": msg.text,
                "from": direction,
                "timestamp": msg.timestamp,
            })

        # Sort oldest first
        result.sort(key=lambda m: m["timestamp"])
        return result

    except Exception as e:
        print(f"  [dm] Error reading thread with @{target_username}: {e}")
        return []


def get_last_message_from_them(client, target_username, our_user_id):
    """
    Get the most recent message from the target in a DM thread.

    Returns:
        str or None
    """
    messages = read_thread_messages(client, target_username, our_user_id, limit=5)
    for msg in reversed(messages):
        if msg["from"] == "them":
            return msg["text"]
    return None


def get_unread_threads(client, our_user_id):
    """
    Get DM threads with unread messages from other users.

    Returns:
        list of dicts: [{"thread_id": str, "username": str, "last_message": str}]
    """
    try:
        threads = client.direct_threads(amount=20)
        unread = []

        for thread in threads:
            if not thread.messages:
                continue

            last_msg = thread.messages[0]

            # Skip if last message is from us
            if str(last_msg.user_id) == str(our_user_id):
                continue

            # Skip if no text
            if not last_msg.text:
                continue

            # Get the other user's username
            other_users = [u for u in thread.users if str(u.pk) != str(our_user_id)]
            if not other_users:
                continue

            unread.append({
                "thread_id": thread.id,
                "username": other_users[0].username,
                "last_message": last_msg.text,
                "timestamp": last_msg.timestamp,
            })

        return unread

    except Exception as e:
        print(f"  [dm] Error getting unread threads: {e}")
        return []


def get_our_user_id(client):
    """Get the logged-in user's ID."""
    try:
        return str(client.user_id)
    except Exception as e:
        print(f"  [dm] Error getting user ID: {e}")
        return None
