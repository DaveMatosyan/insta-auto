"""
Session manager — open/close browser sessions with proxy + fingerprint + cookies.
Core module for consistent identity across logins.

Proxy auto-rotation:
    Each time open_session() is called, it gets a fresh proxy from proxy_manager.
    The proxy manager auto-rotates IPs at random intervals (40-100 min) using
    ProxyShare session IDs — so each account maintains its own rotating IP.
"""

import os
import random
import time
from dataclasses import dataclass
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page

from config import SESSIONS_DIR, BLOCK_IMAGES
from core.utils import parse_proxy_url
from core.stealth import get_stealth_script


@dataclass
class Session:
    """One browser session = one Instagram account."""
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    account: dict


def _cookie_path(username):
    """Path for per-account cookie/state file."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{username}_state.json")


def open_session(account, headless=True, block_images=None, no_proxy=False):
    """
    Launch browser with proxy + fingerprint + cookies (auto-login).

    Args:
        account (dict): Account record from instagram_accounts.json
        headless (bool): Run headless or not
        block_images (bool): Override image blocking (None = use config default)
        no_proxy (bool): Force direct connection (no proxy)

    Returns:
        Session object
    """
    if block_images is None:
        block_images = BLOCK_IMAGES

    fingerprint = account.get("fingerprint", {})
    username = account.get("username", "unknown")
    cookie_file = _cookie_path(username)

    # Static proxy from account's linked proxy (Supabase FK)
    if no_proxy:
        proxy_url = None
    else:
        proxy_url = account.get("proxy_url")

    pw = sync_playwright().start()

    launch_args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions',
        '--disable-sync',
        '--disable-default-apps',
        '--disable-preconnect',
    ]

    browser = pw.chromium.launch(headless=headless, args=launch_args)

    screen = fingerprint.get("screen", {})
    ctx_kwargs = {
        "viewport": {
            "width": screen.get("width", 412),
            "height": screen.get("height", 915),
        },
        "user_agent": fingerprint.get("user_agent",
            "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.39 Mobile Safari/537.36"),
        "locale": "en-US",
        "timezone_id": fingerprint.get("timezone", "America/Los_Angeles"),
        "permissions": [],
        "geolocation": None,
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": fingerprint.get("device_scale_factor", 2.625),
        "extra_http_headers": {
            "Accept-Language": fingerprint.get("accept_language", "en-US,en;q=0.9"),
        },
    }

    if proxy_url:
        ctx_kwargs["proxy"] = parse_proxy_url(proxy_url)

    if os.path.exists(cookie_file):
        ctx_kwargs["storage_state"] = cookie_file

    context = browser.new_context(**ctx_kwargs)
    # Inject stealth script matched to this account's device fingerprint
    context.add_init_script(get_stealth_script(fingerprint))

    if block_images:
        context.route("**/*.{png,jpg,jpeg,gif,webp,svg}", lambda route: route.abort())

    page = context.new_page()

    session = Session(
        playwright=pw,
        browser=browser,
        context=context,
        page=page,
        account=account,
    )

    if os.path.exists(cookie_file):
        print(f"Loaded cookies for @{username}")
    if proxy_url:
        print(f"Proxy: {proxy_url[:40]}...")

    return session


def close_session(session, save_cookies=True):
    """Save cookies and close the browser."""
    username = session.account.get("username", "unknown")
    if save_cookies:
        cookie_file = _cookie_path(username)
        session.context.storage_state(path=cookie_file)
        print(f"Saved cookies for @{username}")

    session.browser.close()
    session.playwright.stop()


def needs_login(page):
    """Check if page shows the login form (cookies expired or not set)."""
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)

        # Wait for JS to fully render (mobile landing page loads first, then real content)
        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(3)

        # If redirected to login page
        if "/accounts/login" in page.url:
            return True

        # Check for actual login form (username input)
        login_input = page.locator('input[name="username"]')
        if login_input.is_visible(timeout=2000):
            return True

        body_text = page.evaluate("document.body.innerText")

        # Logged-in indicators — if ANY found, we're logged in
        logged_in = ["Search", "Home", "Explore", "Reels", "Messages", "Notifications", "Profile", "Create"]
        if any(ind in body_text[:1000] for ind in logged_in):
            return False

        # Mobile landing page detection: if we see "Log in" AND "Sign up" as buttons,
        # this is the unauthenticated landing page
        login_link = page.evaluate("""() => {
            const a = document.querySelector('a[href*="/accounts/login"]');
            return a ? a.textContent.trim() : null;
        }""")
        if login_link and "log in" in login_link.lower():
            return True

        # Last resort: no logged-in indicators at all
        print("No logged-in indicators found, treating as not logged in")
        return True
    except Exception as e:
        print(f"needs_login check error: {e}")
        return True


def do_login(page, username, password):
    """Fill login form, submit, wait for feed."""
    try:
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)

        # Wait for login form to appear
        page.locator('input[name="username"]').wait_for(state="visible", timeout=10000)

        page.locator('input[name="username"]').fill(username)
        time.sleep(random.uniform(0.5, 1.5))
        page.locator('input[name="password"]').fill(password)
        time.sleep(random.uniform(0.5, 1.5))

        # Try multiple login button selectors
        login_clicked = False
        for selector in [
            'div[role="button"][aria-label="Log in"]',
            'button[type="submit"]',
            'button:has-text("Log in")',
            'div[role="button"]:has-text("Log in")',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    login_clicked = True
                    break
            except:
                continue

        if not login_clicked:
            print(f"Could not find login button for @{username}")
            return False

        # Wait for navigation after login (page context may be destroyed briefly)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass
        time.sleep(5)

        # Dismiss any popups (save login info, notifications)
        for _ in range(3):
            try:
                not_now = page.locator('button:has-text("Not Now")').first
                if not_now.is_visible(timeout=2000):
                    not_now.click()
                    time.sleep(2)
            except:
                break

        # Check if login succeeded
        current_url = page.url
        if "/accounts/login" in current_url:
            print(f"Login failed for @{username} (still on login page)")
            return False
        elif "/challenge" in current_url:
            print(f"Login for @{username} requires challenge verification!")
            return False
        else:
            print(f"Logged in as @{username}")
            return True

    except Exception as e:
        # Navigation errors during redirect are expected — check if we ended up logged in
        try:
            time.sleep(3)
            current_url = page.url
            if "/accounts/login" not in current_url and "/challenge" not in current_url:
                print(f"Logged in as @{username} (after redirect)")
                return True
        except:
            pass
        print(f"Login error for @{username}: {e}")
        return False


def ensure_logged_in(session):
    """
    Convenience: check cookies, log in if needed.

    Returns:
        bool: True if authenticated
    """
    page = session.page
    account = session.account
    if needs_login(page):
        print(f"Cookies expired for @{account['username']}, re-authenticating...")
        return do_login(page, account["username"], account["password"])
    else:
        print(f"@{account['username']} already logged in via cookies")
        return True
