"""
Instagram DM operations via Playwright browser automation.
All functions accept a Playwright Page object (logged in).
"""

from core.browser_dm import (
    send_dm,
    read_thread_messages,
    get_last_message_from_them,
    get_unread_threads,
    get_our_username,
)

__all__ = [
    "send_dm",
    "read_thread_messages",
    "get_last_message_from_them",
    "get_unread_threads",
    "get_our_username",
]
