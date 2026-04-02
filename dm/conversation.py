"""
AI conversation engine — Gemini-powered message generation with:
- Temperature variation (0.80-0.95 per call)
- Post-generation validation (banned words, length, em dashes)
- Gaussian delays for human-like timing
- 7-stage state machine support
"""

import json
import random
import re
import time

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    DM_MAX_MESSAGES_BEFORE_DEAD,
    DM_REPLY_ENGAGED,
    DM_REPLY_FAST,
    DM_REPLY_NORMAL,
    DM_REPLY_SLOW,
    DM_REPLY_AFTER_PITCH,
    DM_DISTRACTION_PAUSE_CHANCE,
    DM_DISTRACTION_PAUSE_SEC,
    DM_CONTEXT_SUMMARIZE_AFTER,
)
from dm.prompts import (
    build_opener_prompt,
    build_reply_prompt,
    build_followup_prompt,
    build_classify_prompt,
    build_summary_prompt,
    determine_stage,
)
from dm.storage import (
    get_message_history,
    update_conversation,
)

GEMINI_MODEL = "gemini-2.5-flash"

# Tier 1 banned words — highest AI detection risk
BANNED_WORDS = [
    "delve", "embark", "navigate", "leverage", "foster", "harness", "unlock",
    "unleash", "craft", "elevate", "supercharge", "revolutionize", "resonate",
    "illuminate", "utilize", "vibrant", "robust", "comprehensive", "pivotal",
    "nuanced", "holistic", "seamless", "cutting-edge", "groundbreaking",
    "transformative", "remarkable", "tapestry", "landscape", "realm", "paradigm",
    "synergy", "framework", "trajectory", "game-changer", "absolutely",
    "fascinating", "fantastic", "intriguing", "compelling", "furthermore",
    "moreover", "therefore", "consequently", "in conclusion",
]

BANNED_PHRASES = [
    "it's important to note", "in today's fast-paced", "i'd be happy to",
    "don't hesitate to", "feel free to", "i completely understand",
    "that's a great question", "i'm glad you asked", "hope you're doing well",
    "at the end of the day", "a testament to",
]


def init_gemini():
    """Initialize Gemini client."""
    if not GEMINI_API_KEY:
        raise ValueError("No Gemini API key! Add GEMINI_API_KEY=your-key to .env")
    return genai.Client(api_key=GEMINI_API_KEY)


def _gaussian_delay(min_sec, max_sec):
    """Gaussian delay — more human-like than uniform random."""
    mean = (min_sec + max_sec) / 2
    stddev = (max_sec - min_sec) / 4
    delay = random.gauss(mean, stddev)
    return max(min_sec, min(max_sec, int(delay)))


def _validate_message(text):
    """
    Post-generation validation. Returns cleaned text or None if unfixable.
    Checks: banned words, length, em dashes, AI artifacts.
    """
    if not text:
        return None

    text_lower = text.lower()

    # Check banned words
    for word in BANNED_WORDS:
        if word.lower() in text_lower:
            return None  # Regenerate

    # Check banned phrases
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            return None

    # Remove em dashes (massive AI tell)
    text = text.replace("—", ",").replace("--", ",")

    # Remove markdown bold/italic but keep * for typo corrections like *you're
    import re as _re
    text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold** -> bold
    text = _re.sub(r'(?<!\w)\*(?!\w)', '', text)     # stray * not part of *correction
    # Don't strip underscores — they appear in usernames and natural text

    # Check length — allow up to 120 words total for multi-message replies (with |||)
    if len(text.split()) > 120:
        return None

    # Remove AI prefixes
    for prefix in ["Here's ", "Sure! ", "Of course! ", "Here is "]:
        if text.startswith(prefix):
            text = text[len(prefix):]

    return text.strip()


def _call_gemini(client, prompt, max_retries=3, max_tokens=250, base_temperature=0.85):
    """
    Call Gemini with the new google.genai SDK.
    Uses thinking_budget=0 to prevent thinking tokens eating output.
    """
    for attempt in range(max_retries):
        try:
            temp = random.uniform(
                max(0.80, base_temperature - 0.05),
                min(0.95, base_temperature + 0.10),
            )

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temp,
                    top_p=0.92,
                    top_k=40,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = response.text.strip()

            print(f"  [ai-raw] Gemini returned: {text[:200]}")

            # Clean markdown wrappers
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)

            # Validate
            validated = _validate_message(text.strip())
            if validated:
                print(f"  [ai-validated] Final: {validated[:200]}")
                return validated

            print(f"  [ai] Message failed validation (attempt {attempt+1}), retrying...")
            continue

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                wait = min(15 * (2 ** attempt), 120)
                print(f"  [ai] Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [ai] Gemini error: {e}")
            return None

    print(f"  [ai] Failed after {max_retries} retries")
    return None


def generate_opener(model, target_profile):
    """Generate personalized opener (under 30 words, compliment + question)."""
    prompt = build_opener_prompt(target_profile)
    response = _call_gemini(model, prompt, max_tokens=60, base_temperature=0.85)

    if not response:
        fallbacks = [
            "hey your profile is cool haha where are you from? 😊",
            "omg your pics are fire, do you do photography? 📸",
            "heyy whats good 😊 where are you from",
            "ok random but your profile caught my eye, whats your vibe?",
            "heyy 😊 had to say hi, whats up",
        ]
        response = random.choice(fallbacks)

    return response


def generate_reply(model, conversation, messages_history, target_profile):
    """
    Generate reply using 7-stage state machine.
    Returns (list_of_messages, current_stage) where list_of_messages is 1-3 messages
    to send in sequence (like a real person who double/triple texts).
    """
    messages_sent = conversation.get("messages_sent", 0)

    # Determine current stage
    current_stage = determine_stage(conversation, messages_history)

    # Context compression for long convos
    if len(messages_history) > DM_CONTEXT_SUMMARIZE_AFTER:
        summary = conversation.get("context_summary", "")
        if not summary:
            summary = summarize_conversation(model, messages_history[:-10])
            if summary:
                update_conversation(conversation["id"], context_summary=summary)
        recent = messages_history[-10:]
        context_msg = {"direction": "system", "message_text": f"[Previous conversation summary: {summary}]"}
        messages_for_prompt = [context_msg] + recent
    else:
        messages_for_prompt = messages_history

    prompt = build_reply_prompt(messages_for_prompt, target_profile, messages_sent, current_stage)
    print(f"\n  [ai-prompt] ===== FULL PROMPT =====")
    print(prompt)
    print(f"  [ai-prompt] ===== END PROMPT =====\n")
    response = _call_gemini(model, prompt, max_tokens=250, base_temperature=0.85)

    if not response:
        # Retry once with higher temp and simpler prompt
        simple_prompt = f"""You are Aiko, a flirty 21yo girl on Instagram DMs.
The guy just said something to you. Reply in 2-3 sentences, be flirty and playful.
Ask a question to keep the convo going. All lowercase, casual texting style.
Their last message: "{messages_for_prompt[-1].get('message_text', 'hey') if messages_for_prompt else 'hey'}"
Output ONLY your reply:"""
        response = _call_gemini(model, simple_prompt, max_tokens=120, base_temperature=0.92)

    if not response:
        response = "haha ok wait tell me more about that, im lowkey curious now 😏"

    # Parse ||| or || delimiter — Gemini sometimes uses 2 pipes instead of 3
    if "|||" in response:
        messages = [m.strip() for m in response.split("|||") if m.strip()]
    elif "||" in response:
        messages = [m.strip() for m in response.split("||") if m.strip()]
    else:
        messages = [response]

    return messages, current_stage


def generate_followup(model, conversation, messages_history, attempt_number):
    """Generate follow-up for unresponsive targets. Max 20 words."""
    prompt = build_followup_prompt(messages_history, attempt_number)
    response = _call_gemini(model, prompt, max_tokens=40, base_temperature=0.90)

    if not response:
        if attempt_number == 1:
            fallbacks = [
                "ok random question whats the best show youve watched recently 😂",
                "heyy you alive? 😂",
                "ok so i have a theory abt you 😏 wanna hear it",
            ]
        elif attempt_number == 2:
            fallbacks = [
                "found this crazy sunset spot and thought of you for some reason haha",
                "ok so i just tried this new coffee place and it changed my life lol",
            ]
        else:
            fallbacks = [
                "no worries if timings not right! wishing you the best 🙏",
                "ok last time i bother you i promise 😂 have a good one!",
            ]
        response = random.choice(fallbacks)

    return response


def classify_reply(model, message_text):
    """Classify reply: interested/not_interested/question/sexual/objection/cold/hostile."""
    prompt = build_classify_prompt(message_text)
    response = _call_gemini(model, prompt, max_tokens=20, base_temperature=0.1)

    valid = {"interested", "not_interested", "question", "sexual", "objection", "cold", "hostile"}
    if response and response.lower().strip() in valid:
        return response.lower().strip()

    # Fallback
    text_lower = message_text.lower()
    if any(w in text_lower for w in ["stop", "leave me alone", "not interested", "block", "report"]):
        return "not_interested"
    if any(w in text_lower for w in ["who are you", "bot", "spam", "automated"]):
        return "objection"
    if "?" in message_text:
        return "question"
    if len(message_text.strip()) <= 3:
        return "cold"
    return "interested"


def summarize_conversation(model, messages_history):
    """Summarize conversation for context compression."""
    prompt = build_summary_prompt(messages_history)
    return _call_gemini(model, prompt, max_tokens=150, base_temperature=0.3)


def calculate_reply_delay(conversation, last_message_text, reply_classification=None):
    """
    Calculate reply delay using Gaussian distribution.
    Fast for engaged leads (15-45 sec), normal for others.
    """
    msg_count = conversation.get("messages_sent", 0)
    stage = conversation.get("stage", "opened")

    # Engaged/sexual → reply FAST
    if reply_classification in ("interested", "sexual"):
        base = _gaussian_delay(*DM_REPLY_ENGAGED)

    # Opening messages
    elif msg_count <= 3:
        base = _gaussian_delay(*DM_REPLY_FAST)

    # After pitch
    elif stage == "pitched" or stage == "6_LINK_DELIVERY":
        base = _gaussian_delay(*DM_REPLY_AFTER_PITCH)

    # Double text
    elif conversation.get("last_message_by") == "them":
        base = _gaussian_delay(60, 180)

    # Flirty keywords → play cool
    elif last_message_text and any(w in last_message_text.lower()
        for w in ["cute", "hot", "sexy", "beautiful", "gorgeous", "😍", "🔥", "😏"]):
        base = _gaussian_delay(*DM_REPLY_SLOW)

    # Normal
    else:
        base = _gaussian_delay(*DM_REPLY_NORMAL)

    # 15% distraction pause
    if random.random() < DM_DISTRACTION_PAUSE_CHANCE:
        base += _gaussian_delay(*DM_DISTRACTION_PAUSE_SEC)

    return base


def should_mark_dead(conversation):
    """Check if engaged conversation should die (50 msg limit)."""
    total = (conversation.get("messages_sent") or 0) + (conversation.get("messages_received") or 0)
    return total >= DM_MAX_MESSAGES_BEFORE_DEAD
