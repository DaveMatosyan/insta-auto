"""
Main entry point for Instagram Account Generator
"""

import time
from config import (
    BASE_EMAIL_PREFIX,
    EMAIL_DOMAIN,
    START_NUMBER,
    NUM_ACCOUNTS,
    JSON_FILE,
    POST_CAPTION,
    IMAGES_DIR,
)
from utils import print_section_header
from proxy_manager import assign_proxy, test_proxy
from instagram_creator import create_account


def main():
    """Main function to orchestrate account creation"""

    print_section_header("INSTAGRAM ACCOUNT GENERATOR")
    print(f"Base email: {BASE_EMAIL_PREFIX}+XXX{EMAIL_DOMAIN}")
    print(f"Starting number: {START_NUMBER}")
    print(f"Number of accounts to create: {NUM_ACCOUNTS}")
    print(f"Accounts will be saved to: {JSON_FILE}")
    print(f"Images folder: {IMAGES_DIR} (random selection)")
    print(f"Post caption: {POST_CAPTION}")
    print("="*60 + "\n")

    successful = 0
    failed = 0

    for i in range(NUM_ACCOUNTS):
        email_number = START_NUMBER + i

        print(f"\n\n{'#'*60}")
        print(f"CREATING ACCOUNT {i+1}/{NUM_ACCOUNTS}")
        print(f"{'#'*60}\n")

        # Assign proxy from pool
        proxy_url = assign_proxy()
        if proxy_url:
            print(f"🌐 Assigned proxy: {proxy_url[:50]}...")
            ip = test_proxy(proxy_url)
            if not ip:
                print("⚠️ Proxy test failed — proceeding without proxy")
                proxy_url = None
        else:
            print("⚠️ No proxies available — proceeding without proxy")

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
            print(f"\n⏳ Waiting 10 seconds before next account...")
            time.sleep(10)

    # Final summary
    print_section_header("FINAL SUMMARY")
    print(f"Total accounts attempted: {NUM_ACCOUNTS}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"All account info saved to: {JSON_FILE}")
    print("="*60 + "\n")


main()
