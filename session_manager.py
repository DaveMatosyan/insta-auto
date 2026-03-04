"""
Session manager — open/close browser sessions with proxy + fingerprint + cookies.
Core module for consistent identity across logins.
"""

import os
import random
import time
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page
from config import SESSIONS_DIR, BLOCK_IMAGES
from utils import parse_proxy_url


@dataclass
class Session:
    """One browser session = one Instagram account"""
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    account: dict


# --- Stealth init script (shared) ---
STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'headless', { get: () => false });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Apple Inc.';
        if (parameter === 37446) return 'Apple GPU';
        return getParameter(parameter);
    };
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {
        return originalToDataURL.call(this);
    };
    Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {
        value: async () => []
    });
    delete window.callPhantom;
    delete window.__phantom;
"""


def _cookie_path(username):
    """Path for per-account cookie/state file"""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{username}_state.json")


def open_session(account, headless=True, block_images=None):
    """
    Launch browser with proxy + fingerprint + cookies (auto-login).

    Args:
        account (dict): Account record from instagram_accounts.json
        headless (bool): Run headless or not
        block_images (bool): Override image blocking (None = use config default)

    Returns:
        Session object
    """
    if block_images is None:
        block_images = BLOCK_IMAGES

    proxy_url = account.get("proxy_url")
    fingerprint = account.get("fingerprint", {})
    username = account.get("username", "unknown")
    cookie_file = _cookie_path(username)

    pw = sync_playwright().start()

    # Browser launch args
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

    # Context options
    screen = fingerprint.get("screen", {})
    ctx_kwargs = {
        "viewport": {
            "width": screen.get("width", random.choice([375, 390, 430])),
            "height": screen.get("height", random.choice([812, 844, 932])),
        },
        "user_agent": fingerprint.get("user_agent",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1"),
        "locale": "en-US",
        "timezone_id": fingerprint.get("timezone", "America/Los_Angeles"),
        "permissions": [],
        "geolocation": None,
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": random.choice([2, 3]),
        "extra_http_headers": {
            "Accept-Language": fingerprint.get("accept_language", "en-US,en;q=0.9"),
        },
    }

    # Add proxy if available
    if proxy_url:
        ctx_kwargs["proxy"] = parse_proxy_url(proxy_url)

    # Load cookies if they exist
    if os.path.exists(cookie_file):
        ctx_kwargs["storage_state"] = cookie_file

    context = browser.new_context(**ctx_kwargs)
    context.add_init_script(STEALTH_SCRIPT)

    # Block images for bandwidth savings
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
        print(f"🍪 Loaded cookies for @{username}")
    if proxy_url:
        print(f"🌐 Proxy: {proxy_url[:40]}...")

    return session


def close_session(session, save_cookies=True):
    """Save cookies and close the browser"""
    username = session.account.get("username", "unknown")
    if save_cookies:
        cookie_file = _cookie_path(username)
        session.context.storage_state(path=cookie_file)
        print(f"🍪 Saved cookies for @{username}")

    session.browser.close()
    session.playwright.stop()


def needs_login(page):
    """Check if page shows the login form (cookies expired or not set)"""
    try:
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
        # If login form is visible, we need to log in
        login_input = page.locator('input[name="username"]')
        return login_input.is_visible(timeout=3000)
    except:
        return True


def do_login(page, username, password):
    """Fill login form, submit, wait for feed"""
    try:
        page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)

        page.locator('input[name="username"]').fill(username)
        time.sleep(random.uniform(0.5, 1.5))
        page.locator('input[name="password"]').fill(password)
        time.sleep(random.uniform(0.5, 1.5))

        page.locator('button[type="submit"]').click()
        time.sleep(random.uniform(5, 8))

        # Handle "Save Login Info" prompt
        try:
            not_now = page.locator('button:has-text("Not Now")').first
            if not_now.is_visible(timeout=3000):
                not_now.click()
                time.sleep(2)
        except:
            pass

        # Check if we landed on the feed
        if "/accounts/login" not in page.url:
            print(f"✅ Logged in as @{username}")
            return True
        else:
            print(f"❌ Login failed for @{username}")
            return False
    except Exception as e:
        print(f"❌ Login error for @{username}: {e}")
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
        print(f"🔑 Cookies expired for @{account['username']}, re-authenticating...")
        return do_login(page, account["username"], account["password"])
    else:
        print(f"✅ @{account['username']} already logged in via cookies")
        return True
