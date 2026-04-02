"""
Entry point for Instagram Account Generator.
Replaces the old main.py with updated module imports.
"""

import time
from config import (
    BASE_EMAIL_PREFIX,
    EMAIL_DOMAIN,
    START_NUMBER,
    NUM_ACCOUNTS,
    IMAGES_DIR,
)
from profile.setup import POST_CAPTIONS
from core.utils import print_section_header
from core.proxy import get_available_proxy, test_proxy
from creator.account import create_account
from db.supabase_client import supabase


def _get_next_email_number():
    """Get the next email number by finding the highest used number in Supabase +1."""
    try:
        resp = supabase.table("accounts").select("email").execute()
        max_num = START_NUMBER - 1
        for row in resp.data:
            email = row.get("email", "")
            if "+" in email and "@" in email:
                # Extract number from "redditakk4+1000008@gmail.com"
                num_str = email.split("+")[1].split("@")[0]
                try:
                    num = int(num_str)
                    if num > max_num:
                        max_num = num
                except ValueError:
                    continue
        return max_num + 1
    except Exception as e:
        print(f"Error getting next email number: {e}")
        return START_NUMBER


def main():
    """Main function to orchestrate account creation."""

    start_number = _get_next_email_number()

    print_section_header("INSTAGRAM ACCOUNT GENERATOR")
    print(f"Base email: {BASE_EMAIL_PREFIX}+XXX{EMAIL_DOMAIN}")
    print(f"Starting number: {start_number} (auto-detected)")
    print(f"Number of accounts to create: {NUM_ACCOUNTS}")
    print(f"Accounts will be saved to: Supabase")
    print(f"Images folder: {IMAGES_DIR} (random selection)")
    print(f"Post captions: {len(POST_CAPTIONS)} random options")
    print("="*60 + "\n")

    successful = 0
    failed = 0

    for i in range(NUM_ACCOUNTS):
        email_number = start_number + i

        print(f"\n\n{'#'*60}")
        print(f"CREATING ACCOUNT {i+1}/{NUM_ACCOUNTS}")
        print(f"{'#'*60}\n")

        # Get a proxy with available capacity
        proxy_url = get_available_proxy()
        if proxy_url:
            print(f"Proxy: {proxy_url[:50]}...")
            ip = test_proxy(proxy_url)
            if not ip:
                print("Proxy test failed - proceeding without proxy")
                proxy_url = None
        else:
            print("No proxies with capacity available!")

        if create_account(email_number, proxy_url=proxy_url):
            successful += 1
        else:
            failed += 1
            retry = input(f"\nAccount {email_number} failed. Retry? (y/n): ").lower()
            if retry == 'y':
                if create_account(email_number, proxy_url=proxy_url):
                    successful += 1
                    failed -= 1

        # Wait between accounts (except for the last one)
        if i < NUM_ACCOUNTS - 1:
            print(f"\nWaiting 10 seconds before next account...")
            time.sleep(10)

    # Final summary
    print_section_header("FINAL SUMMARY")
    print(f"Total accounts attempted: {NUM_ACCOUNTS}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"All account info saved to Supabase")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
