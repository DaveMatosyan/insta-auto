"""
Utility functions for Instagram Account Generator
"""

import random
import string
import subprocess
import time


def generate_random_string(length=8):
    """Generate a random string with lowercase letters and digits"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def get_current_ip():
    """Get current IP address to verify VPN connection"""
    try:
        # Try multiple IP checking services
        services = [
            "curl -s ifconfig.me",
            "curl -s icanhazip.com",
            "curl -s api.ipify.org"
        ]
        
        for service in services:
            try:
                result = subprocess.run(service, shell=True, capture_output=True, text=True, timeout=10)
                ip = result.stdout.strip()
                if ip and '.' in ip:  # Basic validation
                    print(f"📍 Current IP: {ip}")
                    return ip
            except:
                continue
        
        print("⚠️ Could not retrieve IP from any service")
        return None
        
    except Exception as e:
        print(f"⚠️ Could not get IP: {e}")
        return None


def print_section_header(text):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(text)
    print("="*60 + "\n")


def print_account_info(email, username, password, fullname):
    """Print account creation information"""
    print(f"\n{'='*60}")
    print("✓ ACCOUNT CREATION COMPLETE!")
    print(f"{'='*60}")
    print(f"EMAIL: {email}")
    print(f"USERNAME: {username}")
    print(f"PASSWORD: {password}")
    print(f"FULL NAME: {fullname}")
    print(f"{'='*60}\n")
