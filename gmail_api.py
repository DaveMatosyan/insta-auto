"""
Gmail API module - Retrieve verification codes without IMAP/CAPTCHA issues
Uses Google's official Gmail API instead of IMAP for better reliability
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

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def authenticate_gmail_api(credentials_file="gmail_credentials.json"):
    """
    Authenticate with Gmail API
    
    Args:
        credentials_file (str): Path to credentials.json from Google Cloud Console
        
    Returns:
        google.auth.credentials.Credentials: Gmail API credentials
    """
    creds = None
    
    # Token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing Gmail API credentials...")
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                print(f"❌ Error: {credentials_file} not found!")
                print("\nSteps to fix:")
                print("1. Download credentials from Google Cloud Console")
                print("2. Save as: gmail_credentials.json")
                print("3. See GMAIL_API_SETUP.txt for details")
                return None
            
            print("📱 Opening browser for Gmail authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        
        # Save the credentials for next time
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    print("✓ Successfully authenticated with Gmail API")
    return creds


def build_gmail_service(creds):
    """
    Build Gmail API service
    
    Args:
        creds: Gmail API credentials
        
    Returns:
        gmail service object
    """
    return build('gmail', 'v1', credentials=creds)


def get_verification_code_from_gmail_api(service, max_retries=15, retry_delay=3):
    """
    Retrieve Instagram verification code from Gmail using API
    
    Args:
        service: Gmail API service
        max_retries (int): Maximum attempts to find the code
        retry_delay (int): Seconds between retries
        
    Returns:
        str: The 6-digit verification code, or None if not found
    """
    import time
    
    try:
        print(f"\n🔍 Fetching verification code from Gmail (API)...")
        print(f"Checking mailbox (max {max_retries} attempts)...\n")
        
        for attempt in range(max_retries):
            try:
                # Search for Instagram verification emails
                results = service.users().messages().list(
                    userId='me',
                    q='from:(Instagram OR no-reply@mail.instagram.com) subject:(code OR verify OR confirmation)',
                    maxResults=5
                ).execute()
                
                messages = results.get('messages', [])
                
                if messages:
                    # Check most recent emails first
                    for msg in messages:
                        try:
                            # Get full message
                            message = service.users().messages().get(
                                userId='me',
                                id=msg['id'],
                                format='full'
                            ).execute()
                            
                            # Extract email body
                            if 'parts' in message['payload']:
                                # Multipart email
                                for part in message['payload']['parts']:
                                    if part['mimeType'] == 'text/plain':
                                        data = part['body'].get('data', '')
                                        if data:
                                            text = base64.urlsafe_b64decode(data).decode('utf-8')
                                        else:
                                            continue
                                    elif part['mimeType'] == 'text/html':
                                        data = part['body'].get('data', '')
                                        if data:
                                            text = base64.urlsafe_b64decode(data).decode('utf-8')
                                        else:
                                            continue
                                    else:
                                        continue
                                    
                                    # Search for 6-digit code
                                    code_match = re.search(r'\b(\d{6})\b', text)
                                    if code_match:
                                        verification_code = code_match.group(1)
                                        print(f"✓ Found verification code: {verification_code}")
                                        return verification_code
                            else:
                                # Single part email
                                data = message['payload']['body'].get('data', '')
                                if data:
                                    text = base64.urlsafe_b64decode(data).decode('utf-8')
                                    code_match = re.search(r'\b(\d{6})\b', text)
                                    if code_match:
                                        verification_code = code_match.group(1)
                                        print(f"✓ Found verification code: {verification_code}")
                                        return verification_code
                        
                        except Exception as e:
                            print(f"⚠️ Error processing message: {e}")
                            continue
                
                # Code not found yet, wait and retry
                if attempt < max_retries - 1:
                    print(f"⏳ Code not found yet. Attempt {attempt + 1}/{max_retries}")
                    print(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            
            except Exception as e:
                print(f"⚠️ API error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        
        print(f"❌ Could not retrieve verification code after {max_retries} attempts")
        return None
        
    except Exception as e:
        print(f"❌ Error fetching verification code: {e}")
        return None


def validate_gmail_api_setup(credentials_file="gmail_credentials.json"):
    """
    Validate Gmail API setup
    
    Args:
        credentials_file (str): Path to credentials.json
        
    Returns:
        bool: True if setup is valid, False otherwise
    """
    print("="*60)
    print("VALIDATING GMAIL API SETUP")
    print("="*60)
    
    # Check credentials file
    if not os.path.exists(credentials_file):
        print(f"\n❌ {credentials_file} not found!")
        print("\nTo fix:")
        print("1. Go to: https://console.cloud.google.com/")
        print("2. Create OAuth 2.0 Client ID (Desktop application)")
        print("3. Download and save as: gmail_credentials.json")
        print("4. Run this script again")
        return False
    
    print("\n✓ credentials.json found")
    
    # Try to authenticate
    try:
        creds = authenticate_gmail_api(credentials_file)
        if not creds:
            return False
        
        # Try to build service
        service = build_gmail_service(creds)
        print("✓ Gmail API service created successfully")
        
        # Try a test query
        print("\n🧪 Testing Gmail API access...")
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        print("✓ Successfully accessed Gmail mailbox")
        
        print("\n" + "="*60)
        print("✓ GMAIL API SETUP IS VALID!")
        print("="*60)
        print("\nYou can now run: python instagram_creator.py\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("✓ credentials.json is in the correct directory")
        print("✓ Gmail API is enabled in Google Cloud Console")
        print("✓ You've granted permission to the app")
        return False

if __name__ == "__main__":
    creds = authenticate_gmail_api()
    # service = build_gmail_service(creds)

    # get_verification_code_from_gmail_api(service)