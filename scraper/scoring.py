"""
Gemini AI scoring — batch profiles for gender + buyer intent classification.
"""

import json
import os
import re
import time

import google.generativeai as genai

from config import PROJECT_ROOT, GEMINI_API_KEY

# --- Gemini AI config ---
GEMINI_MODEL = "gemini-2.5-flash"
AI_BATCH_SIZE = 20


def init_gemini():
    """Initialize Gemini client — key loaded from .env via config."""
    api_key = GEMINI_API_KEY
    if not api_key:
        raise ValueError(
            "No Gemini API key found! Add GEMINI_API_KEY=your-key to .env file"
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def ai_score_batch(model, profiles_batch, comments_map):
    """
    Send a batch of profiles to Gemini for AI scoring.

    Args:
        model: Gemini GenerativeModel instance
        profiles_batch: list of profile dicts
        comments_map: dict {username: comment_text}

    Returns:
        list of dicts with AI scores
    """
    profile_lines = []
    for p in profiles_batch:
        username = p['username']
        comment = comments_map.get(username, '')
        line = (
            f"- @{username} | name: {p.get('fullname', 'N/A')} | "
            f"bio: {p.get('bio', 'N/A')} | "
            f"followers: {p.get('followers', 0)} | following: {p.get('following', 0)} | "
            f"posts: {p.get('posts', 0)} | "
            f"private: {p.get('is_private', False)} | verified: {p.get('is_verified', False)} | "
            f"has_pfp: {p.get('has_custom_pfp', False)} | "
            f"link: {p.get('external_link', '')} | "
            f"comment: {comment[:120]}"
        )
        profile_lines.append(line)

    profiles_text = "\n".join(profile_lines)

    prompt = f"""You are a senior digital marketing analyst specializing in adult content creator monetization (OnlyFans, Fansly). You have 10+ years of experience identifying high-value male subscribers by analyzing their social media behavior. Your conversion predictions are used by top agencies to build targeted follower funnels.

YOUR TASK: You are given a batch of Instagram profiles. These were scraped from the comment sections of popular female fitness models and bikini competitors. Your job is to determine for each profile:

1. Is this a POTENTIAL BUYER — a male who would subscribe and pay for exclusive female content?
2. Give each profile a score from 0 to 10 representing how likely they are to become a paying subscriber.

HOW YOU WORK — Your analysis process for each profile:

Step 1 — GENDER CLASSIFICATION:
You look at username, display name, and bio TOGETHER to determine gender. You know from experience:
- Usernames containing female names (jessica, sarah, maria, bella, nayla, bruna, claudia, sonya, michelle, julia, grace, maddy, dawn, kaela, rhia, nita, mae, yaneth) -> female
- Usernames with "girl", "queen", "mama", "babe", "princess", "goddess", "gurl", "diva", "lady", "bella", "chica", "miss" -> female
- Bio with "mom", "wife", "she/her", "actress", "model", "lash", "nail tech", "beauty", "feminine" -> female
- Bio with IFBB, NPC, bikini pro, fitness competitor, athlete, coach -> usually female competitor (they comment on each other's posts, they are NOT buyers)
- Usernames with male names (john, mike, james, ahmed, carlos, pedro, hermes, shariq, parth, steel) -> male
- Accounts that are clearly brands, shops, meal prep, supplement companies -> business, not a buyer
- When gender is truly unclear -> "unknown"

Step 2 — BUYER INTENT SCORING (0-10):
You analyze behavioral signals that predict whether someone will pay for content:

CRITICAL CONTEXT: These profiles were scraped from comments on FEMALE fitness/bikini model posts. Statistically 70-80% of commenters on these posts are male. So if gender is unclear but the account shows consumer behavior, assume likely male and score accordingly (don't give 0 to unknowns — give them 3-5 based on their signals).

STRONG BUYER SIGNALS (each adds points):
- Male gender confirmed -> base score starts at 5
- Gender unknown but consumer behavior -> base score starts at 3
- following > followers ratio (they consume, don't create) -> +1-2
- Follows 500+ accounts (follows many creators) -> +1
- Less than 50 posts (lurker/viewer, not a poster) -> +1
- Small account under 5000 followers (regular person, not influencer) -> +1
- Comment contains thirsty emojis: fire, heart_eyes, drooling -> +1-2
- Comment contains compliment words: beautiful, gorgeous, stunning, hot, sexy, amazing, perfect -> +1-2
- Has a profile picture (real person, engaged user) -> +1
- Private account with consumer ratio -> still a buyer signal (they hide their activity)

DISQUALIFYING SIGNALS (score 0-1):
- Confirmed female — they don't buy female content -> score 0
- Business/brand account — no individual buyer -> score 1
- IFBB pro, fitness competitor, bikini athlete — they are peers, not customers -> score 0
- Verified celebrity — not a buyer -> score 1
- Bot-like account (0 followers, 0 following, no pfp) -> score 0
- Very high follower count 50k+ (they're creators themselves) -> score 2

PROFILES TO ANALYZE:
{profiles_text}

RESPOND WITH ONLY A RAW JSON ARRAY. No explanation, no markdown formatting, no ```json code blocks.
Each object must have exactly these 4 fields: username, gender, score, reasons.
The "reasons" field MUST list specific signals you found. Never write just "Female." or "Gender unknown." — always explain WHY.

Example:
[{{"username":"john_doe123","gender":"male","score":8,"reasons":"male name John, following(2100)>followers(450), lurker 3 posts, thirsty comment, has pfp"}},{{"username":"jessica.fit","gender":"female","score":0,"reasons":"female name Jessica, IFBB in bio, fitness competitor peer"}}]"""

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()

            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            text = text.strip()

            results = json.loads(text)

            if not isinstance(results, list):
                print(f"      AI returned non-list response, skipping batch")
                return []

            return results

        except json.JSONDecodeError as e:
            print(f"      AI response was not valid JSON: {e}")
            print(f"      Raw response: {text[:300]}")
            return []
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                wait = min(30 * (2 ** attempt), 300)
                print(f"      Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"      AI scoring failed: {e}")
            return []

    print(f"      AI scoring failed after {max_retries} retries (quota exhausted)")
    return []
