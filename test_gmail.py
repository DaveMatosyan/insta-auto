#!/usr/bin/env python
"""
Test Gmail connection before running account creation
Verifies IMAP access and credentials are correct
"""

import imaplib
import sys
from config import GMAIL_EMAIL, GMAIL_PASSWORD


def test_gmail_connection():
    """Test if Gmail IMAP connection works"""
    
    print("="*60)
    print("TESTING GMAIL CONNECTION")
    print("="*60)
    
    # Check if credentials are set
    if GMAIL_PASSWORD == "your_app_password":
        print("\n❌ ERROR: GMAIL_PASSWORD not configured!")
        print("\nSteps to fix:")
        print("1. Get App Password from: https://myaccount.google.com/apppasswords")
        print("2. Open config.py")
        print("3. Update GMAIL_PASSWORD with your 16-character app password")
        print("4. Run this test again")
        return False
    
    print(f"\n📧 Gmail Email: {GMAIL_EMAIL}")
    print(f"🔐 App Password: {'*' * len(GMAIL_PASSWORD)}")
    
    try:
        print("\n🔍 Connecting to Gmail IMAP server...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        print("✓ Connected to imap.gmail.com")
        
        print(f"\n🔓 Logging in as {GMAIL_EMAIL}...")
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        print("✓ Successfully logged in!")
        
        print("\n📂 Fetching mailbox information...")
        status, mailboxes = mail.list()
        print(f"✓ Found {len(mailboxes)} mailboxes")
        
        print("\n📥 Selecting INBOX...")
        status, inbox_count = mail.select("INBOX")
        print(f"✓ INBOX selected")
        print(f"   Messages in INBOX: {inbox_count[0].decode()}")
        
        print("\n🔍 Searching for Instagram emails...")
        status, messages = mail.search(None, 'FROM "Instagram" OR FROM "noreply@instagram.com"')
        
        if messages[0]:
            email_count = len(messages[0].split())
            print(f"✓ Found {email_count} Instagram emails")
        else:
            print("ℹ️ No Instagram emails found")
            print("   (This is OK - you haven't verified accounts yet)")
        
        print("\n🔌 Closing connection...")
        mail.close()
        mail.logout()
        print("✓ Connection closed")
        
        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        print("\nYour Gmail setup is ready. You can now run:")
        print("  python instagram_creator.py")
        print("\nVerification codes will be fetched automatically! 🚀\n")
        
        return True
        
    except imaplib.IMAP4.error as e:
        print(f"\n❌ Gmail connection error: {e}")
        print("\nTroubleshooting:")
        print("1. Verify 2-Step Verification is enabled:")
        print("   https://myaccount.google.com/security")
        print("2. Verify App Password was created:")
        print("   https://myaccount.google.com/apppasswords")
        print("3. Verify IMAP is enabled:")
        print("   https://mail.google.com/mail/u/0/#settings/fwdandpop")
        print("4. Make sure password has no spaces")
        return False
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("✓ GMAIL_EMAIL is correct in config.py")
        print("✓ GMAIL_PASSWORD is your 16-char app password (not regular password)")
        print("✓ 2-Step Verification is enabled on Google Account")
        print("✓ IMAP is enabled in Gmail settings")
        return False


if __name__ == "__main__":
    success = test_gmail_connection()
    sys.exit(0 if success else 1)
