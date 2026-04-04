import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONIOENCODING"] = "utf-8"

from core.storage import get_all_accounts
from core.session import open_session, close_session, ensure_logged_in
from core.utils import human_delay

username = 'aiko_ren_w67a5'
accounts = [a for a in get_all_accounts() if a.get('username') == username]
account = accounts[0]

session = open_session(account, headless=False)
try:
    if not ensure_logged_in(session):
        print('Login failed!')
        sys.exit(1)

    page = session.page
    page.goto('https://www.instagram.com/direct/inbox/', wait_until='domcontentloaded', timeout=30000)
    human_delay(5, 7)

    print(f'URL: {page.url}')

    # Simple debug: get all thread buttons info
    debug = page.evaluate("""() => {
        var results = [];
        var buttons = document.querySelectorAll('div[role="button"]');
        var idx = 0;
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            var pic = btn.querySelector('img[alt="user-profile-picture"], img[draggable="false"]');
            if (!pic) continue;
            var nameEl = btn.querySelector('span[dir="auto"]');
            var name = nameEl ? nameEl.textContent.trim() : 'NO_NAME';
            var html = btn.innerHTML.substring(0, 300);
            var hasUnreadText = html.indexOf('Unread') !== -1;
            results.push({idx: idx, name: name, hasUnreadText: hasUnreadText, htmlSnippet: html});
            idx++;
        }
        return results;
    }""")

    print(f'\nFound {len(debug)} thread buttons:')
    for d in debug:
        marker = ' *** HAS UNREAD TEXT' if d['hasUnreadText'] else ''
        print(f'  [{d["idx"]}] {d["name"]}{marker}')

    # Also dump raw HTML of first 2 threads for inspection
    print('\n--- RAW HTML (first 2 threads) ---')
    for d in debug[:2]:
        print(f'\n[{d["idx"]}] {d["name"]}:')
        print(d['htmlSnippet'])

    # Keep browser open for 30 seconds so user can check
    print('\n\nBrowser stays open for 30s so you can check...')
    time.sleep(30)

finally:
    close_session(session)
    print('Browser closed.')
