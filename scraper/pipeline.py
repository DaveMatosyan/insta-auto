"""
Pipeline orchestrators — scrape-only, score-file, and full scraper modes.
"""

import argparse
import json
import os
import random
import time
from datetime import datetime

from config import (
    TARGET_CREATORS, SCRAPER_MAX_POSTS, SCRAPER_SCORE_PROFILES,
    SCRAPER_MIN_SCORE, PROJECT_ROOT,
)
from db.supabase_client import supabase
from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.utils import human_delay, pick_best_account

from scraper.scraping import scrape_creator
from scraper.profiles import parse_api_user, get_profile_data
from scraper.filtering import pre_filter_profile
from scraper.scoring import init_gemini, ai_score_batch, AI_BATCH_SIZE, GEMINI_MODEL
from scraper.persistence import save_targets, merge_to_tracker, RAW_COMMENTERS_JSON


def run_scrape_only(creators=None, max_posts=None, count=50,
                    headless=True, no_proxy=False, min_score=None):
    """
    Full pipeline with crash-safe incremental saves:
        1. Scrape ~count usernames from creator comments
        2. Process in batches: visit profiles -> pre-filter -> Gemini score -> save
        3. Resume-safe: skips already-processed usernames on restart
    """
    creators = creators or TARGET_CREATORS
    max_posts = max_posts or SCRAPER_MAX_POSTS
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    accounts = get_all_accounts(role="scraper")
    if not accounts:
        print("No accounts available!")
        return

    account = pick_best_account(accounts, role="scraper")

    try:
        gemini_model = init_gemini()
        print(f"Gemini AI ready ({GEMINI_MODEL})")
    except Exception as e:
        print(f"Could not initialize Gemini: {e}")
        return

    already_processed = set()
    try:
        resp = supabase.table('targets_scored').select('username').execute()
        already_processed = {r['username'] for r in resp.data}
    except Exception as e:
        print(f"Warning: could not load already-processed from Supabase: {e}")

    checkpoint_file = os.path.join(PROJECT_ROOT, "scrape_checkpoint.json")
    checkpoint = {"visited": [], "scraped_commenters": {}}
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
            print(f"Loaded checkpoint: {len(checkpoint.get('visited', []))} previously visited")
        except:
            pass
    visited_set = set(checkpoint.get("visited", []))
    visited_set.update(already_processed)

    print(f"\n{'='*60}")
    print(f"SCRAPE -> FILTER -> SCORE PIPELINE")
    print(f"Account: @{account['username']}")
    print(f"Proxy: {'NONE (direct)' if no_proxy else 'auto-rotating'}")
    print(f"Creators: {len(creators)} | Posts/creator: {max_posts}")
    print(f"Target count: {count} raw usernames")
    print(f"Min score: {min_score}")
    print(f"Already processed: {len(visited_set)}")
    print(f"{'='*60}\n")

    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
    if not ensure_logged_in(session):
        print("Could not log in, aborting")
        close_session(session, save_cookies=False)
        return

    page = session.page

    # Set up hover-based profile API interception
    intercepted_profiles: dict = {}

    def _on_response(response):
        url = response.url
        if '/api/v1/users/web_profile_info/' not in url:
            return
        try:
            data = response.json()
            user = (data.get('data', {}).get('user')
                    or data.get('graphql', {}).get('user')
                    or {})
            uname = user.get('username', '')
            if uname:
                intercepted_profiles[uname] = parse_api_user(user)
        except Exception:
            pass

    page.on('response', _on_response)
    print(f"Profile API interception active (hover -> no page visits needed)")

    # PHASE 1: Scrape commenters (or resume from checkpoint)
    saved_commenters = checkpoint.get("scraped_commenters", {})
    if saved_commenters:
        fresh_from_saved = [u for u in saved_commenters.keys() if u not in visited_set]
        if len(fresh_from_saved) >= count:
            print(f"Resuming from checkpoint: {len(fresh_from_saved)} unvisited commenters available, skipping Phase 1")
            all_commenters = saved_commenters
        else:
            print(f"Checkpoint has {len(fresh_from_saved)} unvisited, need {count} -- scraping more...")
            saved_commenters = {}

    if not saved_commenters:
        print(f"\n--- PHASE 1: Scraping commenters (target: {count}) ---\n")
        all_commenters = {}

        for creator in creators:
            try:
                commenters = scrape_creator(page, creator, max_posts)
                all_commenters.update(commenters)
                print(f"   Running total: {len(all_commenters)} unique commenters")
            except Exception as e:
                print(f"Error scraping @{creator}: {e}")

            fresh_so_far = [u for u in all_commenters.keys() if u not in visited_set]
            if len(fresh_so_far) >= count:
                print(f"\nReached {count} fresh usernames -- stopping early")
                break

            if creator != creators[-1]:
                wait = random.uniform(45, 90)
                print(f"Waiting {wait:.0f}s before next creator...")
                time.sleep(wait)

        checkpoint["scraped_commenters"] = all_commenters
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, ensure_ascii=False)
        print(f"Saved {len(all_commenters)} scraped commenters to checkpoint")

    fresh = [u for u in all_commenters.keys() if u not in visited_set]
    usernames_list = fresh[:count]
    print(f"\n--- PHASE 1 DONE: {len(usernames_list)} fresh usernames to process (skipped {len(all_commenters) - len(fresh)} already visited) ---\n")

    if not usernames_list:
        print("No fresh usernames to process! Try scraping different creators.")
        close_session(session, save_cookies=True)
        return

    # PHASE 2+3: Profile data -> pre-filter -> Gemini score -> save
    intercepted_count = len([u for u in usernames_list if u in intercepted_profiles])
    fallback_count = len(usernames_list) - intercepted_count
    print(f"--- PHASE 2+3: Filter + score ({AI_BATCH_SIZE} per batch) ---")
    print(f"    {intercepted_count}/{len(usernames_list)} profiles already captured via hover API")
    print(f"    {fallback_count} profiles need page navigation (fallback)\n")

    targets = []
    total_filtered = 0
    total_females = 0
    total_low = 0
    total_visited = 0
    total_from_hover = 0
    total_from_nav = 0
    filter_reasons = {}

    for chunk_start in range(0, len(usernames_list), AI_BATCH_SIZE):
        chunk_usernames = usernames_list[chunk_start:chunk_start + AI_BATCH_SIZE]
        chunk_num = chunk_start // AI_BATCH_SIZE + 1
        total_chunks = (len(usernames_list) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE

        print(f"\n   === Batch {chunk_num}/{total_chunks} ({len(chunk_usernames)} usernames) ===")

        batch_profiles = []
        batch_comments = {}
        nav_needed = []

        for username in chunk_usernames:
            visited_set.add(username)
            total_visited += 1

            if username in intercepted_profiles:
                profile_data = intercepted_profiles[username]
                total_from_hover += 1
            else:
                nav_needed.append(username)
                profile_data = None

            if profile_data:
                comment = all_commenters.get(username, {}).get('comment', '')
                keep, reason = pre_filter_profile(profile_data, comment)
                if keep:
                    batch_profiles.append(profile_data)
                    batch_comments[username] = comment
                else:
                    total_filtered += 1
                    key = reason.split("'")[0].strip() if "'" in reason else reason
                    filter_reasons[key] = filter_reasons.get(key, 0) + 1
                    print(f"      @{username} -- {reason}")

        if nav_needed:
            print(f"   Navigating to {len(nav_needed)} profiles (not in hover cache)...")
            for i, username in enumerate(nav_needed):
                profile_data = get_profile_data(page, username)
                total_from_nav += 1

                if not profile_data:
                    continue

                comment = all_commenters.get(username, {}).get('comment', '')
                keep, reason = pre_filter_profile(profile_data, comment)
                if keep:
                    batch_profiles.append(profile_data)
                    batch_comments[username] = comment
                else:
                    total_filtered += 1
                    key = reason.split("'")[0].strip() if "'" in reason else reason
                    filter_reasons[key] = filter_reasons.get(key, 0) + 1
                    print(f"      @{username} -- {reason}")

                if i < len(nav_needed) - 1:
                    human_delay(4, 8)

        if nav_needed and chunk_start > 0 and chunk_start % (AI_BATCH_SIZE * 2) == 0:
            wait = random.uniform(20, 40)
            print(f"   Rate limit break ({wait:.0f}s)...")
            time.sleep(wait)

        if total_from_nav > 0 and total_from_nav % 100 == 0:
            wait = random.uniform(60, 120)
            print(f"   Cooldown after {total_from_nav} page navigations ({wait:.0f}s)...")
            time.sleep(wait)

        batch_targets = []
        if batch_profiles:
            print(f"   Scoring {len(batch_profiles)} profiles with Gemini...")
            ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
            ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

            for profile in batch_profiles:
                uname = profile['username']
                ai = ai_map.get(uname, {})
                gender = ai.get('gender', 'unknown')
                score = ai.get('score', 0)
                reasons = ai.get('reasons', 'ai_no_response')

                if gender == 'female':
                    total_females += 1
                    continue
                if score < min_score:
                    total_low += 1
                    continue

                source = all_commenters.get(uname, {})
                target = {
                    **profile,
                    "gender": gender,
                    "score": score,
                    "reasons": reasons[:150],
                    "source_creator": source.get('source_creator', ''),
                    "source_post": source.get('source_post', ''),
                    "comment": batch_comments.get(uname, '')[:100],
                    "scraped_at": datetime.now().isoformat(),
                }
                batch_targets.append(target)
                targets.append(target)

            if batch_targets:
                save_targets(batch_targets)
                merge_to_tracker(batch_targets)
            time.sleep(2)

        checkpoint["visited"] = list(visited_set)
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, ensure_ascii=False)

        print(f"   Batch {chunk_num}: {len(batch_targets)} qualified | Running total: {len(targets)} | Visited: {total_visited}/{len(usernames_list)}")

    close_session(session, save_cookies=True)

    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
        print("Cleared checkpoint file")

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"Profiles processed: {total_visited}")
    print(f"  Via hover API (fast): {total_from_hover}")
    print(f"  Via page navigation (fallback): {total_from_nav}")
    print(f"Pre-filtered out: {total_filtered}")
    for reason, cnt in sorted(filter_reasons.items(), key=lambda x: -x[1]):
        print(f"   {reason}: {cnt}")
    print(f"Sent to Gemini: {total_visited - total_filtered}")
    print(f"Gemini females excluded: {total_females}")
    print(f"Gemini low score excluded: {total_low}")
    print(f"QUALIFIED TARGETS: {len(targets)}")
    print(f"Saved to: Supabase targets_scored table")
    print(f"{'='*60}\n")


def run_score_file(score_file, min_score=None, headless=True, no_proxy=False):
    """Read usernames from a text file, visit each profile, score with Gemini."""
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    with open(score_file, 'r') as f:
        usernames = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not usernames:
        print("No usernames in file!")
        return

    comments_data = {}
    if os.path.exists(RAW_COMMENTERS_JSON):
        with open(RAW_COMMENTERS_JSON, 'r') as f:
            comments_data = json.load(f)

    print(f"\n{'='*60}")
    print(f"SCORE-FILE MODE")
    print(f"Input: {score_file} ({len(usernames)} usernames)")
    print(f"Min score: {min_score}")
    print(f"Batch size: {AI_BATCH_SIZE}")
    print(f"{'='*60}\n")

    try:
        gemini_model = init_gemini()
        print(f"Gemini AI ready ({GEMINI_MODEL})")
    except Exception as e:
        print(f"Could not initialize Gemini: {e}")
        return

    accounts = get_all_accounts(role="scraper")
    if not accounts:
        print("No accounts available!")
        return

    account = pick_best_account(accounts, role="scraper")
    print(f"Using account @{account['username']}")

    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
    if not ensure_logged_in(session):
        print("Could not log in, aborting")
        close_session(session, save_cookies=False)
        return

    page = session.page
    targets = []
    total_females = 0
    total_low = 0

    batch_profiles = []
    batch_comments = {}

    for i, username in enumerate(usernames):
        profile_data = get_profile_data(page, username)
        if profile_data:
            batch_profiles.append(profile_data)
            batch_comments[username] = comments_data.get(username, {}).get('comment', '')

        if i < len(usernames) - 1:
            human_delay(4, 8)
        if i > 0 and i % 25 == 0:
            wait = random.uniform(30, 60)
            print(f"   Rate limit break ({wait:.0f}s)...")
            time.sleep(wait)

        is_last = (i == len(usernames) - 1)
        if len(batch_profiles) >= AI_BATCH_SIZE or (is_last and batch_profiles):
            print(f"\n   Scoring batch ({len(batch_profiles)} profiles, {i+1}/{len(usernames)} done)...")

            ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
            ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

            batch_targets = []
            for profile in batch_profiles:
                uname = profile['username']
                ai = ai_map.get(uname, {})
                gender = ai.get('gender', 'unknown')
                score = ai.get('score', 0)
                reasons = ai.get('reasons', 'ai_no_response')

                if gender == 'female':
                    total_females += 1
                    continue
                if score < min_score:
                    total_low += 1
                    continue

                source = comments_data.get(uname, {})
                target = {
                    **profile,
                    "gender": gender,
                    "score": score,
                    "reasons": reasons[:150],
                    "source_creator": source.get('source_creator', ''),
                    "source_post": source.get('source_post', ''),
                    "comment": source.get('comment', '')[:100],
                    "scraped_at": datetime.now().isoformat(),
                }
                batch_targets.append(target)
                targets.append(target)

            if batch_targets:
                save_targets(batch_targets)
                merge_to_tracker(batch_targets)

            print(f"   Batch: {len(batch_targets)} qualified | Total: {len(targets)}")
            batch_profiles = []
            batch_comments = {}
            time.sleep(2)

    close_session(session, save_cookies=True)

    print(f"\n{'='*60}")
    print(f"SCORING COMPLETE")
    print(f"Profiles visited: {len(usernames)}")
    print(f"Females excluded: {total_females}")
    print(f"Low score excluded: {total_low}")
    print(f"Qualified targets (score >= {min_score}): {len(targets)}")
    print(f"Saved to: Supabase targets_scored table")
    print(f"{'='*60}\n")


def run_scraper(creators=None, max_posts=None, score_profiles=None,
                min_score=None, headless=True, no_proxy=False):
    """
    Main scraper entry point (legacy all-in-one).

    Flow:
        Phase 1: Scrape commenters from creator posts
        Phase 2: Visit each commenter's profile -> collect raw data
        Phase 3: Send batches to Gemini AI for gender/buyer scoring
        Phase 4: Save qualified targets to CSV
    """
    creators = creators or TARGET_CREATORS
    max_posts = max_posts or SCRAPER_MAX_POSTS
    if score_profiles is None:
        score_profiles = SCRAPER_SCORE_PROFILES
    if min_score is None:
        min_score = SCRAPER_MIN_SCORE

    if not creators:
        print("No creators to scrape! Add handles to TARGET_CREATORS in config.py")
        return []

    accounts = get_all_accounts()
    if not accounts:
        print("No accounts available! Create one first with create_accounts.py")
        return []

    account = pick_best_account(accounts)

    if no_proxy:
        print("No-proxy mode: using your own IP for scraping")

    gemini_model = None
    if score_profiles:
        try:
            gemini_model = init_gemini()
            print(f"Gemini AI scoring enabled ({GEMINI_MODEL})")
        except Exception as e:
            print(f"Could not initialize Gemini: {e}")
            return []

    print(f"\n{'='*60}")
    print(f"TARGET SCRAPER")
    print(f"Using account: @{account['username']}")
    print(f"Proxy: {'NONE (direct)' if no_proxy else 'auto-rotating (ProxyShare)'}")
    print(f"Creators to scrape: {len(creators)} accounts")
    print(f"Posts per creator: {max_posts}")
    print(f"Score profiles: {score_profiles} (Gemini AI)")
    print(f"Min score: {min_score}")
    print(f"{'='*60}\n")

    session = open_session(account, headless=headless, block_images=False, no_proxy=no_proxy)
    if not ensure_logged_in(session):
        print("Could not log in, aborting")
        close_session(session, save_cookies=False)
        return []

    page = session.page
    all_commenters = {}

    for creator in creators:
        try:
            commenters = scrape_creator(page, creator, max_posts)
            all_commenters.update(commenters)
        except Exception as e:
            print(f"Error scraping @{creator}: {e}")

        if creator != creators[-1]:
            wait = random.uniform(45, 90)
            print(f"Waiting {wait:.0f}s before next creator...")
            time.sleep(wait)

    print(f"\n{'='*60}")
    print(f"Phase 1 complete: {len(all_commenters)} unique commenters")
    print(f"{'='*60}\n")

    targets = []
    total_profiles_collected = 0
    total_females_excluded = 0
    total_low_score = 0

    if score_profiles and all_commenters:
        usernames = list(all_commenters.keys())
        print(f"Processing {len(usernames)} profiles (batch size: {AI_BATCH_SIZE})...\n")

        batch_profiles = []
        batch_comments = {}

        for i, username in enumerate(usernames):
            profile_data = get_profile_data(page, username)
            if profile_data:
                batch_profiles.append(profile_data)
                batch_comments[username] = all_commenters[username].get('comment', '')
                total_profiles_collected += 1

            if i < len(usernames) - 1:
                human_delay(4, 8)

            if i > 0 and i % 25 == 0:
                wait = random.uniform(30, 60)
                print(f"   Rate limit break ({wait:.0f}s)...")
                time.sleep(wait)

            if i > 0 and i % 100 == 0:
                wait = random.uniform(120, 180)
                print(f"   Long cooldown ({wait:.0f}s) to avoid ban...")
                time.sleep(wait)

            is_last = (i == len(usernames) - 1)
            if len(batch_profiles) >= AI_BATCH_SIZE or (is_last and batch_profiles):
                print(f"\n   Scoring batch ({len(batch_profiles)} profiles, {total_profiles_collected}/{len(usernames)} total)...")

                ai_results = ai_score_batch(gemini_model, batch_profiles, batch_comments)
                ai_map = {r['username']: r for r in ai_results if isinstance(r, dict)}

                batch_targets = []
                for profile in batch_profiles:
                    uname = profile['username']
                    ai = ai_map.get(uname, {})
                    gender = ai.get('gender', 'unknown')
                    score = ai.get('score', 0)
                    reasons = ai.get('reasons', 'ai_no_response')

                    if gender == 'female':
                        total_females_excluded += 1
                        continue
                    if score < min_score:
                        total_low_score += 1
                        continue

                    target = {
                        **profile,
                        "gender": gender,
                        "score": score,
                        "reasons": reasons[:150],
                        "source_creator": all_commenters.get(uname, {}).get('source_creator', ''),
                        "source_post": all_commenters.get(uname, {}).get('source_post', ''),
                        "comment": batch_comments.get(uname, '')[:100],
                        "scraped_at": datetime.now().isoformat(),
                    }
                    batch_targets.append(target)
                    targets.append(target)

                if batch_targets:
                    save_targets(batch_targets)
                    merge_to_tracker(batch_targets)

                print(f"   Batch done: {len(batch_targets)} qualified, {len(targets)} total so far")

                batch_profiles = []
                batch_comments = {}
                time.sleep(2)

        print(f"\n   Finished: {total_profiles_collected} profiles processed")

    elif not score_profiles:
        no_score_targets = []
        for username, data in all_commenters.items():
            target = {
                "username": username,
                "profile_url": f"https://www.instagram.com/{username}/",
                "score": 0,
                "followers": 0, "following": 0, "follow_ratio": 0,
                "posts": 0, "fullname": "", "bio": "", "external_link": "",
                "is_private": False, "is_verified": False,
                "has_story": False, "has_custom_pfp": False,
                "gender": "unknown", "reasons": "not_scored",
                "source_creator": data['source_creator'],
                "source_post": data['source_post'],
                "comment": data.get('comment', '')[:100],
                "scraped_at": datetime.now().isoformat(),
            }
            no_score_targets.append(target)
            targets.append(target)

        if no_score_targets:
            save_targets(no_score_targets)
            merge_to_tracker(no_score_targets)

    close_session(session, save_cookies=True)

    print(f"\n{'='*60}")
    print(f"SCRAPER RESULTS")
    print(f"Total commenters found: {len(all_commenters)}")
    print(f"Profiles collected: {total_profiles_collected}")
    print(f"Females excluded: {total_females_excluded}")
    print(f"Low score excluded: {total_low_score}")
    print(f"AI-qualified targets (score >= {min_score}): {len(targets)}")
    print(f"{'='*60}\n")

    return targets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape high-intent targets from competitor creators")
    parser.add_argument("--creators", nargs="+", help="Creator handles to scrape")
    parser.add_argument("--posts", type=int, default=None, help="Posts per creator (default: 12)")
    parser.add_argument("--no-score", action="store_true", help="Skip profile scoring")
    parser.add_argument("--min-score", type=int, default=None, help="Min quality score 0-10 (default: 4)")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--no-proxy", action="store_true", help="Direct connection (no proxy)")

    parser.add_argument("--scrape-only", action="store_true",
                        help="Step 1: Just scrape usernames -> raw_commenters.txt")
    parser.add_argument("--count", type=int, default=50,
                        help="How many usernames to collect (for --scrape-only, default: 50)")
    parser.add_argument("--score-file", type=str, default=None,
                        help="Step 3: Score usernames from file (e.g. raw_commenters.txt)")
    args = parser.parse_args()

    if args.scrape_only:
        run_scrape_only(
            creators=args.creators,
            max_posts=args.posts,
            count=args.count,
            headless=not args.visible,
            no_proxy=args.no_proxy,
            min_score=args.min_score,
        )
    elif args.score_file:
        run_score_file(
            score_file=args.score_file,
            min_score=args.min_score,
            headless=not args.visible,
            no_proxy=args.no_proxy,
        )
    else:
        run_scraper(
            creators=args.creators,
            max_posts=args.posts,
            score_profiles=not args.no_score,
            min_score=args.min_score,
            headless=not args.visible,
            no_proxy=args.no_proxy,
        )


if __name__ == "__main__":
    main()
