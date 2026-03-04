"""
Cupid Bot — DM follow-back handler (stub).

Will be built after MVP follow system works.
Needs: Fanvue link + scripted vs LLM preference.
"""

from session_manager import open_session, close_session, ensure_logged_in


def check_follow_backs(session):
    """Check notifications for new followers (stub)"""
    # TODO: Navigate to notifications, parse follow-back events
    raise NotImplementedError("check_follow_backs not yet implemented")


def send_dm(session, username, message):
    """Send a DM to a user (stub)"""
    # TODO: Navigate to DMs, compose and send message
    raise NotImplementedError("send_dm not yet implemented")
