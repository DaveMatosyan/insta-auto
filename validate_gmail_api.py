#!/usr/bin/env python
"""
Quick validation script for Gmail API setup
"""

import sys
from gmail_api import validate_gmail_api_setup

if __name__ == "__main__":
    success = validate_gmail_api_setup()
    sys.exit(0 if success else 1)
