"""
Account storage and management (JSON file operations)
"""

import json
import os
from config import JSON_FILE


def load_accounts():
    """
    Load existing accounts from JSON file
    
    Returns:
        list: List of account dictionaries
    """
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    return json.loads(content)
        except json.JSONDecodeError:
            print(f"⚠️ Warning: {JSON_FILE} is corrupted, starting fresh")
            pass
    return []


def save_account(email, username, password):
    """
    Save account credentials to JSON file
    
    Args:
        email (str): Account email
        username (str): Instagram username
        password (str): Account password
    """
    accounts = load_accounts()
    accounts.append({
        "email": email,
        "username": username,
        "password": password
    })
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved account to {JSON_FILE}")


def get_account_count():
    """
    Get the number of saved accounts
    
    Returns:
        int: Number of accounts in JSON file
    """
    return len(load_accounts())
