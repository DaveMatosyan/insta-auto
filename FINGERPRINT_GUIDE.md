# Browser Fingerprint Feature Documentation

## Overview
The Instagram account creator now generates and saves unique browser fingerprints for each account. This ensures that you can login with the same browser characteristics (device model, user agent, timezone, etc.) every time.

## What is a Browser Fingerprint?

A browser fingerprint includes:
- **User Agent**: Unique identifier for the browser and OS
- **Device Model**: iPhone 13, iPhone 14, iPhone 15, etc.
- **Screen Resolution**: Display dimensions
- **Timezone**: Geographic timezone setting
- **Accept-Language**: Language preference
- **WebGL Vendor/Renderer**: GPU information

These characteristics help make automated browser interactions look more natural and consistent.

## How It Works

### 1. **Account Creation with Fingerprint**
When you create a new Instagram account using `instagram_creator.py`:
- A random fingerprint is automatically generated
- The fingerprint is applied to the Playwright browser context
- The fingerprint is saved in `instagram_accounts.json` alongside the account credentials

### 2. **Saved Fingerprint Data**
Each saved account now includes:
```json
{
  "email": "user@gmail.com",
  "username": "ariasky12345",
  "password": "Pass1234567!",
  "fingerprint": {
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2...",
    "device_model": "iPhone 14",
    "screen": {"width": 390, "height": 844},
    "webgl": {"vendor": "Apple Inc.", "renderer": "Apple A16 Bionic GPU"},
    "timezone": "America/Los_Angeles",
    "platform": "iPhone",
    "accept_language": "en-US,en;q=0.9",
    "generated_timestamp": 1707427200.0
  }
}
```

### 3. **Login with Fingerprint**
Use the included `login_with_fingerprint.py` to login with saved fingerprints:

```python
from login_with_fingerprint import login_with_fingerprint, list_accounts_with_fingerprints

# List all saved accounts with their fingerprints
list_accounts_with_fingerprints()

# Login with a specific account using its saved fingerprint
username = "ariasky12345"
password = "Pass1234567!"
page, browser, context = login_with_fingerprint(username, password, headless=False)

if page:
    # Perform automation with the logged-in session
    # The browser will use the exact same fingerprint as during account creation
    time.sleep(60)
    browser.close()
```

## Files Modified/Created

### Modified Files:
1. **`utils.py`** - Added `generate_browser_fingerprint()` function
2. **`account_storage.py`** - Updated `save_account()` to store fingerprints
3. **`instagram_creator.py`** - Updated to generate and use fingerprints during account creation

### New Files:
1. **`login_with_fingerprint.py`** - Module to login with saved fingerprints

## Usage Examples

### Example 1: Creating an Account
```python
from instagram_creator import create_account

# Create account - fingerprint is automatically generated and saved
create_account(email_number=1, use_vpn_country="US")
```

The fingerprint will be automatically generated and saved to `instagram_accounts.json`.

### Example 2: Viewing Saved Fingerprints
```python
from login_with_fingerprint import list_accounts_with_fingerprints

list_accounts_with_fingerprints()
```

Output:
```
============================================================
📋 Saved Accounts with Fingerprints:
============================================================

1. Username: ariasky12345
   Email: user+1@gmail.com
   Device: iPhone 14
   User Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 18_2...
   Timezone: America/Los_Angeles

============================================================
```

### Example 3: Logging In with Fingerprint
```python
from login_with_fingerprint import login_with_fingerprint
import time

# Login to an account - will use the exact fingerprint from creation
page, browser, context = login_with_fingerprint("ariasky12345", "Pass1234567!", headless=False)

if page:
    print("Successfully logged in with matching fingerprint!")
    # The browser context will have the same user agent, device, timezone, etc.
    # as when the account was created
    
    # Do further automation here
    
    time.sleep(60)  # Keep browser open for 60 seconds
    browser.close()
```

## Benefits

✅ **Consistency**: Each account maintains the same "browser identity"  
✅ **Authenticity**: Fingerprints make the account look less bot-like  
✅ **Tracking**: Historical record of browser characteristics used  
✅ **Reproducibility**: Can recreate the exact browser environment anytime  
✅ **Account Reliability**: Consistent fingerprints reduce detection risk  

## JSON Structure Example

```json
[
  {
    "email": "user+1@gmail.com",
    "username": "ariasky12345",
    "password": "Pass1234567!",
    "fingerprint": {
      "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15...",
      "accept_language": "en-US,en;q=0.9",
      "screen": {
        "width": 390,
        "height": 844
      },
      "webgl": {
        "vendor": "Apple Inc.",
        "renderer": "Apple A16 Bionic GPU"
      },
      "timezone": "America/Los_Angeles",
      "platform": "iPhone",
      "device_model": "iPhone 14",
      "generated_timestamp": 1707427200.0
    }
  }
]
```

## Advanced Customization

### Custom Fingerprints
You can also manually edit the fingerprint in `instagram_accounts.json` if needed:

```json
{
  "user_agent": "custom_user_agent_string",
  "device_model": "iPhone 15 Pro",
  "timezone": "Europe/London",
  "accept_language": "en-GB,en;q=0.8"
}
```

### Retrieving Specific Fingerprints
```python
from account_storage import get_fingerprint_by_username

fingerprint = get_fingerprint_by_username("ariasky12345")
print(fingerprint['device_model'])  # Output: iPhone 14
print(fingerprint['timezone'])      # Output: America/Los_Angeles
```

## Notes

- Fingerprints are randomly generated each time an account is created
- No two accounts will have identical fingerprints (unless manually created)
- The fingerprint includes GPU spoofing to avoid WebGL detection
- Timezone and locale are set consistently with the fingerprint
- Change `generate_browser_fingerprint()` in `utils.py` to customize fingerprint generation
