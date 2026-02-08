"""
Main entry point for Instagram Account Generator
"""

import time
from config import (
    BASE_EMAIL_PREFIX,
    EMAIL_DOMAIN,
    START_NUMBER,
    NUM_ACCOUNTS,
    VPN_CHANGE_INTERVAL,
    OPENVPN_PATH,
    VPN_CONFIGS_DIR,
    JSON_FILE,
    PROFILE_PIC_PATH,
    POST_IMAGE_PATH,
    POST_CAPTION
)
from utils import get_current_ip, print_section_header
from vpn_manager import disconnect_openvpn
from instagram_creator import create_account


def main():
    """Main function to orchestrate account creation"""
    
    print_section_header("INSTAGRAM ACCOUNT GENERATOR")
    print(f"Base email: {BASE_EMAIL_PREFIX}+XXX{EMAIL_DOMAIN}")
    print(f"Starting number: {START_NUMBER}")
    print(f"Number of accounts to create: {NUM_ACCOUNTS}")
    print(f"VPN change interval: Every {VPN_CHANGE_INTERVAL} accounts")
    print(f"OpenVPN path: {OPENVPN_PATH}")
    print(f"Config directory: {VPN_CONFIGS_DIR}")
    print(f"Accounts will be saved to: {JSON_FILE}")
    print(f"Profile picture: {PROFILE_PIC_PATH if PROFILE_PIC_PATH else 'Not set'}")
    print(f"Post image: {POST_IMAGE_PATH if POST_IMAGE_PATH else 'Not set'}")
    print(f"Post caption: {POST_CAPTION if POST_IMAGE_PATH else 'N/A'}")
    print("="*60 + "\n")
    
    # Check initial IP
    print("\n📍 Checking initial IP address (without VPN)...")
    initial_ip = get_current_ip()
    
    successful = 0
    failed = 0
    
    for i in range(NUM_ACCOUNTS):
        email_number = START_NUMBER + i
        
        # Create account
        print(f"\n\n{'#'*60}")
        print(f"CREATING ACCOUNT {i+1}/{NUM_ACCOUNTS}")
        print(f"{'#'*60}\n")
        
        # Show current connection status
        print("📊 Current Connection Status:")
        
        if create_account(
            email_number,
        ):
            successful += 1
        else:
            failed += 1
            retry = input(f"\nAccount {email_number} failed. Retry? (y/n): ").lower()
            if retry == 'y':
                if create_account(
                    email_number,
                ):
                    successful += 1
                    failed -= 1
        
        # Wait between accounts (except for the last one)
        if i < NUM_ACCOUNTS - 1:
            print(f"\n⏳ Waiting 10 seconds before next account...")
            time.sleep(10)
    
    # Disconnect VPN after all accounts are created
    print_section_header("ALL ACCOUNTS CREATED - DISCONNECTING VPN")
    
    # Verify disconnection
    time.sleep(3)
    final_ip = get_current_ip()
    if final_ip == initial_ip:
        print(f"✅ VPN disconnected successfully (IP restored to {initial_ip})")
    else:
        print(f"⚠️ IP may still be different: {final_ip} vs {initial_ip}")
    
    # Final summary
    print_section_header("FINAL SUMMARY")
    print(f"Total accounts attempted: {NUM_ACCOUNTS}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"All account info saved to: {JSON_FILE}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
