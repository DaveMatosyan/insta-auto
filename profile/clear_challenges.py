"""
Clear Instagram challenges for all accounts by logging in via browser.
Browser stays open long enough for you to complete challenges manually.

Usage: python -m profile.clear_challenges [--max-accounts N]
"""

import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage import get_all_accounts
from core.session import open_session, close_session
from core.proxy import get_fresh_proxy


def clear_challenge_for_account(account):
    """
    Open browser, attempt login, let user complete challenge.
    Returns True if account ends up logged in.
    """
    username = account["username"]
    password = account["password"]
    email = account.get("email", "")

    print(f"\n{'='*50}")
    print(f"  Account: @{username}")
    print(f"  Email: {email}")
    print(f"{'='*50}")

    # Delete stale cookies to force fresh login
    cookie_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "sessions", f"{username}_state.json"
    )
    if os.path.exists(cookie_file):
        os.remove(cookie_file)
        print(f"  Cleared old cookies")

    session = open_session(account, headless=False, block_images=False)
    page = session.page

    try:
        # Go to login page
        print("  Navigating to login (this may take a while with proxy)...")
        page.goto("https://www.instagram.com/accounts/login/",
                   wait_until="domcontentloaded", timeout=90000)
        print("  Page loaded. Waiting for form to render...")
        time.sleep(15)

        # Try to find and fill login form (mobile or desktop)
        filled = False
        for u_sel, p_sel in [
            ('input[name="username"]', 'input[name="password"]'),
            ('input[name="email"]', 'input[name="pass"]'),
        ]:
            try:
                u_el = page.locator(u_sel).first
                if u_el.is_visible(timeout=5000):
                    u_el.fill(username)
                    time.sleep(1)
                    page.locator(p_sel).first.fill(password)
                    time.sleep(1)
                    filled = True
                    break
            except:
                continue

        if not filled:
            print("  Could not find login form. Browser stays open 60s...")
            time.sleep(60)
            close_session(session, save_cookies=False)
            return False

        # Click login
        for sel in [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Log in")',
            'div[role="button"]:has-text("Log in")',
            'div[role="button"][aria-label="Log in"]',
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    break
            except:
                continue

        print("  Login submitted. Waiting for Instagram response (slow proxy)...")
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except:
            pass
        time.sleep(15)

        url = page.url
        print(f"  Current URL: {url[:80]}")

        # Check what happened
        if "/challenge" in url:
            print(f"\n  >>> CHALLENGE DETECTED! <<<")
            print(f"  >>> Complete the verification in the browser window.")
            print(f"  >>> Check email: {email}")
            print(f"  >>> You have 3 MINUTES to complete it...")
            # Wait and poll every 5 seconds for 3 minutes
            for i in range(36):  # 36 * 5 = 180 seconds = 3 min
                time.sleep(5)
                try:
                    current = page.url
                    if "/challenge" not in current:
                        print(f"  >>> Challenge completed!")
                        break
                except:
                    pass
                remaining = (36 - i - 1) * 5
                if remaining > 0 and (i + 1) % 6 == 0:  # Print every 30s
                    print(f"  >>> {remaining}s remaining...")
            time.sleep(5)
            url = page.url

        # Dismiss popups
        for _ in range(5):
            try:
                btn = page.locator('button:has-text("Not Now")').first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    time.sleep(3)
            except:
                break

        url = page.url
        if "/accounts/login" not in url and "/challenge" not in url:
            print(f"  SUCCESS! @{username} is logged in.")
            print(f"  Browser stays open 60s so you can verify...")
            time.sleep(60)
            close_session(session, save_cookies=True)
            return True
        else:
            print(f"  FAILED. URL: {url[:80]}")
            print(f"  Browser stays open 60s -- check what happened...")
            time.sleep(60)
            # Check again after waiting
            try:
                url = page.url
                if "/accounts/login" not in url and "/challenge" not in url:
                    print(f"  Now logged in after wait!")
                    close_session(session, save_cookies=True)
                    return True
            except:
                pass
            close_session(session, save_cookies=False)
            return False

    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Browser stays open 60s...")
        time.sleep(60)
        try:
            if "/accounts/login" not in page.url and "/challenge" not in page.url:
                print(f"  Actually logged in despite error!")
                close_session(session, save_cookies=True)
                return True
        except:
            pass
        close_session(session, save_cookies=False)
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clear Instagram challenges")
    parser.add_argument("--max-accounts", type=int, default=None)
    parser.add_argument("--account", type=str, default=None,
                        help="Specific account username to clear")
    args = parser.parse_args()

    accounts = [a for a in get_all_accounts() if a.get("role") != "scraper"]

    if args.account:
        accounts = [a for a in accounts if a["username"] == args.account]
        if not accounts:
            print(f"Account @{args.account} not found")
            return

    if args.max_accounts:
        accounts = accounts[:args.max_accounts]

    print(f"\nChallenge Clearing: {len(accounts)} accounts")
    print(f"A browser will open for each account.")
    print(f"If you see a challenge, complete it in the browser.")
    print(f"You'll have up to 3 minutes per challenge.\n")

    results = {"ok": [], "fail": []}

    for i, account in enumerate(accounts):
        print(f"\n--- Account {i+1}/{len(accounts)} ---")
        if clear_challenge_for_account(account):
            results["ok"].append(account["username"])
        else:
            results["fail"].append(account["username"])

        if i < len(accounts) - 1:
            print(f"\n  Next account in 10s...")
            time.sleep(10)

    print(f"\n{'='*50}")
    print(f"CHALLENGE CLEARING RESULTS")
    print(f"  OK ({len(results['ok'])}): {', '.join(results['ok']) or 'none'}")
    print(f"  FAIL ({len(results['fail'])}): {', '.join(results['fail']) or 'none'}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
