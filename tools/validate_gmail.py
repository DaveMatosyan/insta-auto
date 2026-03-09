#!/usr/bin/env python
"""
Quick validation script for Gmail API setup.
"""

import os
import sys

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from creator.gmail_api import validate_gmail_api_setup

if __name__ == "__main__":
    success = validate_gmail_api_setup()
    sys.exit(0 if success else 1)
