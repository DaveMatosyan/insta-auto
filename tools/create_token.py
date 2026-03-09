#!/usr/bin/env python3
"""
create_token.py

Interactive helper to create `token.pickle` for the Gmail API.

Run this from the project root where `gmail_credentials.json` lives.
It prints an auth URL, you open it, sign in, then paste the redirect URL
or just the `code` value. The script exchanges the code and saves
`token.pickle` (used by the main app).
"""
import os
import sys
import pickle
from urllib.parse import urlparse, parse_qs
from google_auth_oauthlib.flow import InstalledAppFlow

# Add project root to path so config imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_ROOT

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDS_FILE = os.path.join(PROJECT_ROOT, "gmail_credentials.json")
OUT_FILE = os.path.join(PROJECT_ROOT, "token.pickle")


def main():
    if not os.path.exists(CREDS_FILE):
        print(f"❌ {CREDS_FILE} not found.")
        print("Place the OAuth desktop client JSON in the project root and try again.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES, redirect_uri='http://localhost')

    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    print("\nOpen this URL in your browser and sign in (use your test user account):\n")
    print(auth_url)
    print("\nAfter allowing access, copy the full redirect URL from the browser's address bar")
    print("and paste it here (or paste just the 'code' parameter).\n")

    redirect = input("Paste redirect URL or code: ").strip()

    # If user pasted full URL, extract code
    if 'code=' in redirect:
        parsed = urlparse(redirect)
        code = parse_qs(parsed.query).get('code', [None])[0]
    else:
        code = redirect

    if not code:
        print("No code found. Make sure you paste the full redirect URL containing '?code=...' or the code itself.")
        return

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(OUT_FILE, 'wb') as f:
            pickle.dump(creds, f)
        print(f"\n✅ Saved credentials to {OUT_FILE}")
        print("You can now run the main script that needs Gmail access.")
    except Exception as e:
        print(f"❌ Error exchanging code for token: {e}")


if __name__ == '__main__':
    main()
