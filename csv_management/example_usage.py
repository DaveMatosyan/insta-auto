"""
Example: Use username manager with Instagram account creation
This shows how to integrate the tracker with your workflow
"""

from username_manager import UsernameTracker


def create_insta_account_with_tracking(email_number, use_vpn_country=None):
    """
    Example of how to use the username tracker with account creation.
    Replace this with your actual account creation logic.
    """
    
    # Initialize tracker
    tracker = UsernameTracker()
    
    # Get next unused username
    username = tracker.get_next_unused()
    if not username:
        print("❌ No unused usernames available!")
        return False
    
    print(f"\n{'='*60}")
    print(f"Creating account #{email_number}")
    print(f"Email: {email_number}@domain.com")
    print(f"Username: {username}")
    if use_vpn_country:
        print(f"VPN Location: {use_vpn_country}")
    print(f"{'='*60}\n")
    
    try:
        # YOUR ACCOUNT CREATION LOGIC HERE
        # ... (run your Instagram account creation code)
        # ...
        
        print(f"✓ Account created successfully with username: {username}")
        
        # Mark username as used after successful account creation
        tracker.mark_as_used(username)
        return True
        
    except Exception as e:
        print(f"❌ Failed to create account: {e}")
        # Don't mark as used if account creation failed
        return False


def batch_create_accounts(num_accounts, use_vpn=False):
    """
    Create multiple accounts using the username tracker
    """
    tracker = UsernameTracker()
    
    # Check available usernames
    unused = tracker.get_unused_usernames()
    if len(unused) < num_accounts:
        print(f"⚠️ Only {len(unused)} unused usernames available, but {num_accounts} requested!")
        return False
    
    print(f"Starting batch creation of {num_accounts} accounts...")
    print(f"Using usernames from tracker...\n")
    
    successful = 0
    failed = 0
    
    for i in range(num_accounts):
        account_num = i + 1
        print(f"\n{'='*60}")
        print(f"Batch: Account {account_num}/{num_accounts}")
        print(f"{'='*60}")
        
        # Get next unused username
        username = tracker.get_next_unused()
        if not username:
            print("❌ No more unused usernames!")
            break
        
        print(f"Username: {username}")
        
        # YOUR ACCOUNT CREATION CODE HERE
        # success = create_insta_account_with_tracking(account_num, use_vpn)
        
        # For demo purposes, we'll just mark as used
        print(f"[Demo] Marking {username} as used...")
        tracker.mark_as_used(username)
        
        successful += 1
    
    print(f"\n{'='*60}")
    print(f"Batch Complete!")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"{'='*60}\n")


def show_tracker_status():
    """Display current tracker status"""
    tracker = UsernameTracker()
    tracker.get_status()
    
    # Show first 20 unused
    unused = tracker.get_unused_usernames(limit=20)
    print(f"Next 20 unused usernames:")
    print("-" * 50)
    for i, username in enumerate(unused, 1):
        print(f"{i:2d}. {username}")


# Example commands
if __name__ == "__main__":
    # Show status
    print("📊 SHOWING TRACKER STATUS")
    show_tracker_status()
    
    # Example: Create batch accounts (COMMENTED OUT - uncomment to use)
    # print("\n📦 CREATING BATCH ACCOUNTS")
    # batch_create_accounts(num_accounts=5, use_vpn=False)
    
    # Example: Mark specific username as used (COMMENTED OUT - uncomment to use)
    # tracker = UsernameTracker()
    # tracker.mark_as_used("zalalagram")
    # tracker.mark_as_used("gary_b_runs")
