"""
Gmail API module — retrieve verification codes without IMAP/CAPTCHA issues.
Uses Google's official Gmail API instead of IMAP for better reliability.
"""

import os
import base64
import re
import pickle

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.api_core import retry
from googleapiclient.discovery import build

from config import PROJECT_ROOT

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Token + credentials live in project root
_TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.pickle")


def authenticate_gmail_api(credentials_file=None):
    """
    Authenticate with Gmail API.

    Args:
        credentials_file (str): Path to credentials.json from Google Cloud Console

    Returns:
        google.auth.credentials.Credentials: Gmail API credentials
    """
    if credentials_file is None:
        from config import GMAIL_CREDENTIALS_FILE
        credentials_file = GMAIL_CREDENTIALS_FILE

    creds = None

    if os.path.exists(_TOKEN_PATH):
        with open(_TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing Gmail API credentials...")
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                print(f"Error: {credentials_file} not found!")
                print("\nSteps to fix:")
                print("1. Download credentials from Google Cloud Console")
                print("2. Save as: gmail_credentials.json")
                return None

            print("Opening browser for Gmail authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(_TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    print("Successfully authenticated with Gmail API")
    return creds


def build_gmail_service(creds):
    """Build Gmail API service."""
    return build('gmail', 'v1', credentials=creds)


def _extract_verification_code(text):
    """
    Extract Instagram 6-digit verification code from email text.
    Avoids matching email address numbers (like +100000@gmail.com).

    Strategy:
    1. Look for code near context words (confirm, verify, code, use)
    2. Exclude numbers that appear in email addresses
    3. Prefer standalone 6-digit numbers not adjacent to @ or +
    """
    # Remove email addresses to avoid matching numbers in them
    cleaned = re.sub(r'[\w.+-]+@[\w.-]+', '', text)

    # Strategy 1: Look for code near context words
    # Matches patterns like "code is 123456" or "123456 is your code" or "use 123456"
    context_patterns = [
        r'(?:code|confirm|verify|enter|use|is)\s*(?::|is)?\s*(\d{6})\b',
        r'\b(\d{6})\s*(?:is your|as your|to confirm|to verify)',
        r'>\s*(\d{6})\s*<',  # Code between HTML tags
    ]

    for pattern in context_patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return match.group(1)

    # Strategy 2: Find all 6-digit numbers in cleaned text, pick the first
    # that doesn't look like part of an address/phone
    all_codes = re.findall(r'\b(\d{6})\b', cleaned)
    for code in all_codes:
        # Skip if it looks like a year range or common non-code number
        if code.startswith('20') and int(code) < 203000:
            continue
        return code

    return None


def get_verification_code_from_gmail_api(service, max_retries=15, retry_delay=3, after_timestamp=None):
    """
    Retrieve Instagram verification code from Gmail using API.

    Args:
        service: Gmail API service
        max_retries (int): Maximum attempts to find the code
        retry_delay (int): Seconds between retries
        after_timestamp (int|float): Unix timestamp — only fetch emails received after this time.
                                     Pass int(time.time()) just before triggering login to avoid stale codes.

    Returns:
        str: The 6-digit verification code, or None if not found
    """
    import time

    try:
        print(f"\nFetching verification code from Gmail (API)...")
        print(f"Checking mailbox (max {max_retries} attempts)...\n")

        # Build Gmail search query — filter to emails after timestamp if provided
        base_q = 'from:(Instagram OR no-reply@mail.instagram.com) subject:(code OR verify OR confirmation)'
        if after_timestamp:
            # Gmail after: filter uses Unix epoch seconds
            base_q += f' after:{int(after_timestamp)}'
            import datetime
            ts_str = datetime.datetime.fromtimestamp(after_timestamp).strftime('%H:%M:%S')
            print(f"  (Only checking emails received after {ts_str})")

        for attempt in range(max_retries):
            try:
                results = service.users().messages().list(
                    userId='me',
                    q=base_q,
                    maxResults=5
                ).execute()

                messages = results.get('messages', [])

                if messages:
                    for msg in messages:
                        try:
                            message = service.users().messages().get(
                                userId='me',
                                id=msg['id'],
                                format='full'
                            ).execute()

                            # Collect all text from the email
                            email_text = ""

                            if 'parts' in message['payload']:
                                for part in message['payload']['parts']:
                                    if part['mimeType'] in ('text/plain', 'text/html'):
                                        data = part['body'].get('data', '')
                                        if data:
                                            email_text += base64.urlsafe_b64decode(data).decode('utf-8') + "\n"
                            else:
                                data = message['payload']['body'].get('data', '')
                                if data:
                                    email_text = base64.urlsafe_b64decode(data).decode('utf-8')

                            if email_text:
                                code = _extract_verification_code(email_text)
                                if code:
                                    print(f"Found verification code: {code}")
                                    return code

                        except Exception as e:
                            print(f"Error processing message: {e}")
                            continue

                if attempt < max_retries - 1:
                    print(f"Code not found yet. Attempt {attempt + 1}/{max_retries}")
                    print(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

            except Exception as e:
                print(f"API error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        print(f"Could not retrieve verification code after {max_retries} attempts")
        return None

    except Exception as e:
        print(f"Error fetching verification code: {e}")
        return None


def validate_gmail_api_setup(credentials_file=None):
    """Validate Gmail API setup."""
    if credentials_file is None:
        from config import GMAIL_CREDENTIALS_FILE
        credentials_file = GMAIL_CREDENTIALS_FILE

    print("="*60)
    print("VALIDATING GMAIL API SETUP")
    print("="*60)

    if not os.path.exists(credentials_file):
        print(f"\n{credentials_file} not found!")
        print("\nTo fix:")
        print("1. Go to: https://console.cloud.google.com/")
        print("2. Create OAuth 2.0 Client ID (Desktop application)")
        print("3. Download and save as: gmail_credentials.json")
        return False

    print("\ncredentials.json found")

    try:
        creds = authenticate_gmail_api(credentials_file)
        if not creds:
            return False

        service = build_gmail_service(creds)
        print("Gmail API service created successfully")

        print("\nTesting Gmail API access...")
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        print("Successfully accessed Gmail mailbox")

        print("\n" + "="*60)
        print("GMAIL API SETUP IS VALID!")
        print("="*60)
        return True

    except Exception as e:
        print(f"\nError: {e}")
        return False


if __name__ == "__main__":
    creds = authenticate_gmail_api()
