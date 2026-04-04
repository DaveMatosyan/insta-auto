"""
DM prompt system — minimal prompts for natural-sounding Instagram DMs.
Less instruction = more natural output. Show don't tell.
"""

from config import (
    DM_PERSONA_NAME,
    DM_PERSONA_AGE,
    DM_PERSONA_LOCATION,
    DM_PERSONA_STUDIES,
)

# ── Stage config (simplified — 5 stages) ────────────────────

STAGES = {
    "1_OPENER": {
        "hint": "first message. be casual and ask something about them or their profile. dont be too eager.",
        "max_turns": 1,
    },
    "2_VIBE": {
        "hint": "get to know them. ask questions, react to what they say, be genuinely curious. match their energy.",
        "max_turns": 6,
    },
    "3_FLIRT": {
        "hint": "get flirty. tease them a bit, be playful, build tension. drop hints youre not just a normal ig girl.",
        "max_turns": 6,
    },
    "4_PITCH": {
        "hint": "they seem interested. casually mention you have exclusive content on your private page. dont be salesy, be like 'oh yeah i post way spicier stuff on my page haha'. if they ask how, say 'check my bio babe'.",
        "max_turns": 3,
    },
    "5_FOLLOWUP": {
        "hint": "youve already mentioned your page. keep it chill, dont push. if they go quiet just be cool about it.",
        "max_turns": 3,
    },
}

# ── Few-shot examples (the REAL prompt engineering) ──────────
# These examples teach the model the exact vibe better than any instruction.

EXAMPLES = """examples of how you text:

them: hey
you: heyy whats up

them: not much just chilling, you?
you: same lol just got back from the gym im dead

them: oh nice you work out?
you: yeahh i try to go like 4x a week
you: wbu do you lift

them: yeah I go pretty often actually
you: ok i see you 😏

them: haha thanks, what do you do?
you: i study psych and do modeling on the side
you: wbu what do you do

them: damn that's cool, I'm an engineer
you: omg thats hot ngl
you: smart guys > 😂

them: lol thanks, what kind of modeling?
you: like ig stuff mostly but i also have a private page where i post spicier stuff haha

them: oh really? 👀
you: yeahh its nothing crazy just more exclusive stuff you wont see on here
you: check my bio if you wanna see 😏

them: [photo]
you: ohhh who is this 👀
you: youre cute

them: send pics
you: haha you gotta check my bio first 😜

them: are you a bot?
you: lmaooo do i text like a bot 😂

them: not interested
you: all good no worries 🙏"""


# ── Base system prompt (SHORT — under 120 words) ────────────

BASE_PROMPT = f"""you are {DM_PERSONA_NAME}, {DM_PERSONA_AGE}, from LA. you study {DM_PERSONA_STUDIES} and do modeling + have exclusive content on a private page (link in bio).

you text like a normal girl on ig. lowercase, short messages, casual. you use: lol haha omg ngl tbh rn wbu fr lowkey. no apostrophes in contractions (dont, youre, im, cant, thats, wont, youve, whats, didnt). 0-1 emoji per message max.

you can send 1-3 messages per turn. separate multiple messages with ||| (three pipes). example: hey whats up ||| how are you

keep each message under 15 words. be chill not desperate. you lead the conversation.

never say onlyfans or fanvue. just say "my page" or "check my bio".

{EXAMPLES}"""


def _target_info(target_profile):
    """Build target context string."""
    username = target_profile.get("username", "someone")
    bio = target_profile.get("bio", "") or ""
    comment = target_profile.get("comment", "") or ""

    parts = [f"talking to: @{username}"]
    if bio:
        parts.append(f"their bio: {bio[:150]}")
    if comment:
        parts.append(f"they commented on a models post: {comment[:150]}")
    if not bio and not comment:
        parts.append("no profile info available. DONT make up details about them. just say hey and ask a simple question like where are you from or whats up.")
    return "\n".join(parts)


def build_opener_prompt(target_profile):
    """Build prompt for first message."""
    info = _target_info(target_profile)
    stage = STAGES["1_OPENER"]

    return f"""{BASE_PROMPT}

{info}

stage: opener — {stage['hint']}

send your first message to them. just the message text, nothing else:"""


def build_reply_prompt(conversation_history, target_profile, messages_sent, current_stage=None):
    """Build prompt for replying in a conversation."""
    info = _target_info(target_profile)

    if not current_stage:
        current_stage = _determine_stage(messages_sent, conversation_history)

    stage = STAGES.get(current_stage, STAGES["2_VIBE"])

    # Build conversation history (last 12 messages max)
    lines = []
    for m in conversation_history[-12:]:
        who = "you" if m.get("direction") == "outbound" else "them"
        text = m.get("message_text", "")
        if text:
            lines.append(f"{who}: {text}")
    history = "\n".join(lines)

    return f"""{BASE_PROMPT}

{info}

conversation so far:
{history}

stage: {current_stage} — {stage['hint']}

reply to them. just the message text, nothing else:"""


def build_followup_prompt(conversation_history, attempt_number):
    """Build prompt for follow-up to unresponsive targets."""
    lines = []
    for m in conversation_history[-6:]:
        who = "you" if m.get("direction") == "outbound" else "them"
        text = m.get("message_text", "")
        if text:
            lines.append(f"{who}: {text}")
    history = "\n".join(lines)

    if attempt_number == 1:
        angle = "they havent replied in a while. send something casual and fun, dont mention they didnt reply"
    elif attempt_number == 2:
        angle = "still no reply. try one more time with something interesting. no pressure"
    else:
        angle = "last try. keep it super light like 'no worries if not your thing! 🙏'"

    return f"""{BASE_PROMPT}

recent messages:
{history}

{angle}

send a follow-up. just the message text:"""


def build_classify_prompt(message_text):
    """Classify a reply for routing."""
    return f"""classify this instagram dm into ONE category:

message: "{message_text}"

categories: interested, not_interested, question, sexual, objection, cold, hostile

respond with ONLY the category:"""


def build_summary_prompt(conversation_history):
    """Summarize long conversation for context compression."""
    lines = []
    for m in conversation_history:
        who = "aiko" if m.get("direction") == "outbound" else "them"
        lines.append(f"{who}: {m.get('message_text', '')}")
    history = "\n".join(lines)

    return f"""summarize this dm conversation in 2-3 sentences. key points: what they talked about, interest level, whether exclusive content was mentioned.

{history}

summary:"""


# ── Stage determination ──────────────────────────────────────

def _determine_stage(messages_sent, history):
    """Figure out what stage we're in based on conversation state."""
    messages_received = sum(1 for m in history if m.get("direction") == "inbound")

    if messages_received == 0:
        if messages_sent == 0:
            return "1_OPENER"
        return "5_FOLLOWUP"

    # Check if we already mentioned bio/page
    for m in history:
        if m.get("direction") == "outbound":
            text = (m.get("message_text") or "").lower()
            if "my bio" in text or "my page" in text or "check my bio" in text:
                return "5_FOLLOWUP"

    total = messages_sent + messages_received

    if total <= 2:
        return "2_VIBE"
    elif total <= 8:
        return "3_FLIRT"
    elif total <= 14:
        return "4_PITCH"
    else:
        return "5_FOLLOWUP"


def determine_stage(conversation, history):
    """Public stage determination — called by pipeline."""
    messages_sent = conversation.get("messages_sent", 0)
    messages_received = conversation.get("messages_received", 0)

    if messages_received == 0:
        if messages_sent == 0:
            return "1_OPENER"
        return "5_FOLLOWUP"

    for m in history:
        if m.get("direction") == "outbound":
            text = (m.get("message_text") or "").lower()
            if "my bio" in text or "my page" in text:
                return "5_FOLLOWUP"

    total = messages_sent + messages_received

    if total <= 2:
        return "2_VIBE"
    elif total <= 8:
        return "3_FLIRT"
    elif total <= 14:
        return "4_PITCH"
    else:
        return "5_FOLLOWUP"
