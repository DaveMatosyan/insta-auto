"""
VPN connection management using OpenVPN
"""

import os
import subprocess
import time
from config import OPENVPN_PATH, VPN_CONFIGS_DIR, VPN_CREDENTIALS_FILE, VPN_CONFIG_FILES


# Global variable to track OpenVPN process
openvpn_process = None


def connect_openvpn(country):
    """
    Connect to OpenVPN using config file
    
    Args:
        country (str): Country code to connect to
        
    Returns:
        bool: True if connection successful, False otherwise
    """
    global openvpn_process
    
    try:
        # Get config file for country
        if country not in VPN_CONFIG_FILES:
            print(f"❌ No config file defined for {country}")
            return False
        
        config_file = VPN_CONFIG_FILES[country]
        config_path = os.path.join(VPN_CONFIGS_DIR, config_file)
        
        # Check if config file exists
        if not os.path.exists(config_path):
            print(f"❌ Config file not found: {config_path}")
            print(f"   Please download it from https://account.protonvpn.com/downloads")
            return False
        
        # Check if credentials file exists
        if not os.path.exists(VPN_CREDENTIALS_FILE):
            print(f"❌ Credentials file not found: {VPN_CREDENTIALS_FILE}")
            print("   Create a file with your OpenVPN username on line 1 and password on line 2")
            return False
        
        print(f"\n🔒 Connecting to OpenVPN ({country})...")
        print(f"   Config: {config_file}")
        
        # Build OpenVPN command
        cmd = [
            OPENVPN_PATH,
            "--config", config_path,
            "--auth-user-pass", VPN_CREDENTIALS_FILE,
            "--auth-nocache"
        ]
        
        # Start OpenVPN process (it runs in background)
        openvpn_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Wait for connection to establish
        print("⏳ Waiting for VPN connection to establish...")
        time.sleep(15)  # OpenVPN usually takes 10-15 seconds to connect
        
        # Check if process is still running (means connection succeeded)
        if openvpn_process.poll() is None:
            print("✓ OpenVPN process started successfully!")
            time.sleep(5)  # Extra time for connection to stabilize
            return True
        else:
            print("❌ OpenVPN process terminated unexpectedly")
            stdout, stderr = openvpn_process.communicate()
            print(f"Output: {stdout.decode()}")
            print(f"Error: {stderr.decode()}")
            return False
        
    except FileNotFoundError:
        print(f"❌ OpenVPN not found at: {OPENVPN_PATH}")
        print("   Please install OpenVPN from: https://openvpn.net/community-downloads/")
        return False
    except Exception as e:
        print(f"❌ Error connecting to OpenVPN: {e}")
        return False


def disconnect_openvpn():
    """Disconnect from OpenVPN"""
    global openvpn_process
    
    try:
        if openvpn_process and openvpn_process.poll() is None:
            print("\n🔓 Disconnecting from OpenVPN...")
            openvpn_process.terminate()
            time.sleep(3)
            
            # Force kill if still running
            if openvpn_process.poll() is None:
                openvpn_process.kill()
                time.sleep(2)
            
            print("✓ OpenVPN disconnected!")
            openvpn_process = None
        else:
            print("⚠️ No active OpenVPN connection")
            
    except Exception as e:
        print(f"⚠️ Error disconnecting OpenVPN: {e}")
