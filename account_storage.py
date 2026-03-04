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


def save_account(email, username, password, fingerprint=None, proxy_url=None):
    """
    Save account credentials, fingerprint, and proxy to JSON file

    Args:
        email (str): Account email
        username (str): Instagram username
        password (str): Account password
        fingerprint (dict): Browser fingerprint data (optional)
        proxy_url (str): Assigned proxy URL (optional)
    """
    accounts = load_accounts()
    account_data = {
        "email": email,
        "username": username,
        "password": password
    }

    if fingerprint:
        account_data["fingerprint"] = fingerprint
    if proxy_url:
        account_data["proxy_url"] = proxy_url

    accounts.append(account_data)
    _save_all(accounts)
    print(f"✓ Saved account to {JSON_FILE}")


def _save_all(accounts):
    """Write full accounts list to JSON"""
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)


def update_account(username, **fields):
    """
    Update any fields on an existing account.

    Args:
        username (str): Account to update
        **fields: Key-value pairs to set (e.g. proxy_url="http://...")

    Returns:
        bool: True if account was found and updated
    """
    accounts = load_accounts()
    for account in accounts:
        if account.get("username") == username:
            account.update(fields)
            _save_all(accounts)
            print(f"✓ Updated account '{username}': {list(fields.keys())}")
            return True
    print(f"⚠️ Account '{username}' not found")
    return False


def get_all_accounts():
    """Return full list of all accounts"""
    return load_accounts()


def get_account_by_username(username):
    """
    Get account data by username
    
    Args:
        username (str): Instagram username to search for
        
    Returns:
        dict: Account data including fingerprint, or None if not found
    """
    accounts = load_accounts()
    for account in accounts:
        if account.get("username") == username:
            return account
    return None


def get_fingerprint_by_username(username):
    """
    Get browser fingerprint for a specific account
    
    Args:
        username (str): Instagram username
        
    Returns:
        dict: Browser fingerprint data, or None if not found
    """
    account = get_account_by_username(username)
    if account:
        return account.get("fingerprint")
    return None


def get_account_count():
    """
    Get the number of saved accounts
    
    Returns:
        int: Number of accounts in JSON file
    """
    return len(load_accounts())
