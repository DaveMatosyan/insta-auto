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


def generate_browser_fingerprint():
    """
    Generate a random browser fingerprint for authentication
    Includes user agent, headers, and browser characteristics
    
    Returns:
        dict: Browser fingerprint data
    """
    # Common iPhone user agents
    iphone_user_agents = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    ]
    
    # Accept language variations
    languages = [
        "en-US,en;q=0.9",
        "en-US,en;q=0.8",
        "en;q=0.9,en-US;q=0.8",
    ]
    
    # Screen resolutions for different iPhone models
    screen_resolutions = [
        {"width": 390, "height": 844},   # iPhone 13/14/15
        {"width": 430, "height": 932},   # iPhone 14/15 Pro Max
        {"width": 375, "height": 667},   # iPhone 8
        {"width": 414, "height": 896},   # iPhone 11
    ]
    
    # WebGL vendor variations
    webgl_vendors = [
        {"vendor": "Apple Inc.", "renderer": "Apple A16 Bionic GPU"},
        {"vendor": "Apple Inc.", "renderer": "Apple A15 Bionic GPU"},
        {"vendor": "Apple Inc.", "renderer": "Apple A14 Bionic GPU"},
    ]
    
    # Random selection from available options
    fingerprint = {
        "user_agent": random.choice(iphone_user_agents),
        "accept_language": random.choice(languages),
        "screen": random.choice(screen_resolutions),
        "webgl": random.choice(webgl_vendors),
        "timezone": "America/Los_Angeles",
        "platform": "iPhone",
        "device_model": random.choice(["iPhone 13", "iPhone 14", "iPhone 15", "iPhone 14 Pro", "iPhone 15 Pro"]),
        "generated_timestamp": time.time()
    }
    
    return fingerprint
