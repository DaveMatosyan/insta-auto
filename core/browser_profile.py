"""
Browser-based profile operations via Playwright.
Replaces instagrapi account_edit / photo_upload with real browser interactions.
"""

import os
import random
import time

from core.utils import human_delay


NAV_TIMEOUT = 30000
ELEMENT_TIMEOUT = 15000


def _dismiss_modals(page):
    """Dismiss any popups/modals that might block the page (login info, notifications, etc.)."""
    for dismiss_text in ["Not now", "Not Now"]:
        try:
            btn = page.locator(f'button:has-text("{dismiss_text}"), div[role="button"]:has-text("{dismiss_text}")').first
            if btn.is_visible(timeout=3000):
                btn.click()
                human_delay(1, 2)
                return
        except Exception:
            continue

    # Try X / Close button
    try:
        close_btn = page.locator('div[role="dialog"] button[aria-label="Close"], svg[aria-label="Close"]').first
        if close_btn.is_visible(timeout=2000):
            close_btn.click()
            human_delay(1, 2)
    except Exception:
        pass


def update_bio(page, bio_text, website_url=None):
    """
    Update Instagram bio and website link via browser.

    Args:
        page: Playwright Page (logged in)
        bio_text: new bio text
        website_url: optional website/linktree URL

    Returns:
        bool: True if updated successfully
    """
    try:
        page.goto("https://www.instagram.com/accounts/edit/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)
        _dismiss_modals(page)

        # Fill bio
        bio_filled = False
        for selector in [
            'textarea[id="pepBio"]',
            'textarea[name="biography"]',
            'textarea[aria-label*="Bio"]',
            'textarea[aria-label*="bio"]',
            'textarea',
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=5000):
                    el.fill("")
                    human_delay(0.5, 1)
                    el.fill(bio_text)
                    bio_filled = True
                    print(f"  [profile] Bio filled: {bio_text[:50]}...")
                    break
            except Exception:
                continue

        if not bio_filled:
            print("  [profile] Could not find bio textarea")
            return False

        # Fill website if provided
        if website_url:
            for selector in [
                'input[id="pepWebsite"]',
                'input[name="website"]',
                'input[aria-label*="Website"]',
                'input[name="external_url"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=3000):
                        el.fill("")
                        human_delay(0.3, 0.5)
                        el.fill(website_url)
                        print(f"  [profile] Website: {website_url}")
                        break
                except Exception:
                    continue

        human_delay(1, 2)

        # Click Submit / Save
        saved = False
        for btn_text in ["Submit", "Save", "Done"]:
            try:
                btn = page.locator(f'button:has-text("{btn_text}"), div[role="button"]:has-text("{btn_text}")').first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    human_delay(3, 5)
                    saved = True
                    print(f"  [profile] Bio saved")
                    break
            except Exception:
                continue

        if not saved:
            # Try form submit
            try:
                page.locator('form button[type="submit"]').first.click()
                human_delay(3, 5)
                saved = True
                print(f"  [profile] Bio saved (form submit)")
            except Exception:
                print("  [profile] Could not find Save button for bio")

        return saved

    except Exception as e:
        print(f"  [profile] Error updating bio: {e}")
        return False


def upload_profile_pic(page, image_path):
    """
    Upload a profile picture via browser.

    Args:
        page: Playwright Page (logged in)
        image_path: path to image file

    Returns:
        bool: True if uploaded
    """
    try:
        page.goto("https://www.instagram.com/accounts/edit/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)
        _dismiss_modals(page)

        # Click "Change profile photo" / avatar area
        change_clicked = False
        for text in ["Change profile photo", "Change photo", "Edit picture or avatar"]:
            try:
                el = page.locator(f'text="{text}"').first
                if el.is_visible(timeout=3000):
                    el.click()
                    human_delay(2, 3)
                    change_clicked = True
                    break
            except Exception:
                continue

        if not change_clicked:
            # Try clicking avatar image
            for selector in [
                'img[data-testid="user-avatar"]',
                'header img',
                'form img',
                'button img',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=3000):
                        el.click()
                        human_delay(2, 3)
                        change_clicked = True
                        break
                except Exception:
                    continue

        # Look for "Upload Photo" in the menu that appeared
        try:
            upload_item = page.locator('text="Upload Photo"').first
            if upload_item.is_visible(timeout=5000):
                upload_item.click()
                human_delay(1, 2)
        except Exception:
            pass

        # Find file input and upload
        file_inputs = page.locator('input[type="file"]')
        file_count = file_inputs.count()

        if file_count > 0:
            file_inputs.first.set_input_files(image_path)
            human_delay(4, 6)

            # Click Save/Done/Apply if needed
            for btn_text in ["Save", "Done", "Apply", "Next", "Submit"]:
                try:
                    btn = page.locator(f'button:has-text("{btn_text}"), div[role="button"]:has-text("{btn_text}")').first
                    if btn.is_visible(timeout=5000):
                        btn.click()
                        human_delay(3, 5)
                        break
                except Exception:
                    continue

            print(f"  [profile] Profile pic uploaded: {os.path.basename(image_path)}")
            return True
        else:
            print("  [profile] No file input found for profile pic upload")
            return False

    except Exception as e:
        print(f"  [profile] Error uploading profile pic: {e}")
        return False


def upload_post(page, image_path, caption=""):
    """
    Upload a photo post via browser.

    Strategy: Navigate directly to /create/select/ which is the POST creation
    flow (not story). This avoids the Create dropdown menu entirely.

    Flow:
      1. Go to /create/select/ (post creation page)
      2. Upload image via file input
      3. Click Next through crop/filter screens
      4. Add caption
      5. Click Share

    Args:
        page: Playwright Page (logged in)
        image_path: path to image file
        caption: post caption

    Returns:
        bool: True if posted
    """
    try:
        # Go directly to post creation URL — skips the Create dropdown entirely
        page.goto("https://www.instagram.com/create/select/",
                  wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        human_delay(3, 5)
        _dismiss_modals(page)

        # Check if we got redirected to home (means URL didn't work)
        current = page.url
        if "/create" not in current:
            print(f"  [profile] /create/select/ redirected to {current}, trying Create button...")
            # Fallback: click Create in sidebar
            page.goto("https://www.instagram.com/",
                      wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
            human_delay(2, 3)
            _dismiss_modals(page)

            # Click the Create/New post link in sidebar
            create_clicked = False
            for selector in [
                'a[href="/create/select/"]',
                'svg[aria-label="New post"]',
                'a[aria-label="New post"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=5000):
                        el.click()
                        human_delay(2, 4)
                        create_clicked = True
                        break
                except Exception:
                    continue

            if not create_clicked:
                # JS fallback — click element with "Create" text
                page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('a, div[role="button"], span');
                        for (const el of els) {
                            const text = (el.textContent || '').trim().toLowerCase();
                            const label = (el.getAttribute('aria-label') || '').toLowerCase();
                            if ((text === 'create' || text === 'new post' || label === 'new post')
                                && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                human_delay(2, 4)

            # If a dropdown appeared, click "Post" specifically
            try:
                # Look for dropdown items — match exact "Post" not "Repost"
                post_option = page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('a, div[role="button"], span, div[role="menuitem"]');
                        for (const el of items) {
                            const text = (el.textContent || '').trim();
                            if (text === 'Post' && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if post_option:
                    print("  [profile] Selected 'Post' from create menu")
                    human_delay(2, 3)
            except Exception:
                pass

        # If we somehow ended up in story creation, abort and retry via direct URL
        if "/creation/" in page.url or "story" in page.url.lower():
            print("  [profile] Detected story mode, closing and retrying...")
            try:
                page.keyboard.press("Escape")
                human_delay(1, 2)
                discard = page.locator('button:has-text("Discard")').first
                if discard.is_visible(timeout=3000):
                    discard.click()
                    human_delay(1, 2)
            except Exception:
                pass
            print("  [profile] Could not open post creation (stuck in story mode)")
            return False

        # Step 2: Upload image via file input
        # Click "Select from computer" if the dialog shows it
        for sel_text in ["Select from computer", "Select from gallery", "Select"]:
            try:
                btn = page.locator(f'button:has-text("{sel_text}")').first
                if btn.is_visible(timeout=3000):
                    btn.click()
                    human_delay(1, 2)
                    break
            except Exception:
                continue

        # Find file input — in post creation dialog there should be exactly one
        file_input = page.locator('input[type="file"][accept*="image"]').first
        try:
            file_input.set_input_files(image_path)
        except Exception:
            # Fallback: try any file input
            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(image_path)

        human_delay(3, 5)
        print(f"  [profile] Image uploaded: {os.path.basename(image_path)}")

        # Verify we're not in story mode after upload
        if "/creation/" in page.url or "story" in page.url.lower():
            print("  [profile] File input triggered story mode, aborting")
            return False

        # Step 3: Click Next through crop and filter screens (2 times)
        for step_name in ["Crop", "Filter"]:
            human_delay(1, 2)
            # Try button click
            next_clicked = False
            for selector in [
                'button:has-text("Next")',
                'div[role="button"]:has-text("Next")',
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=5000):
                        btn.click()
                        next_clicked = True
                        print(f"  [profile] Clicked Next ({step_name})")
                        break
                except Exception:
                    continue

            if not next_clicked:
                # JS fallback
                page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('button, div[role="button"]');
                        for (const el of els) {
                            if (el.textContent?.trim() === 'Next' && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)

            human_delay(2, 4)

        # Step 4: Add caption
        if caption:
            caption_filled = False
            for selector in [
                'div[aria-label="Write a caption..."][contenteditable]',
                'textarea[aria-label="Write a caption..."]',
                'div[role="textbox"][contenteditable]',
                'div[contenteditable="true"]',
                'textarea[placeholder*="caption"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=5000):
                        el.click()
                        human_delay(0.5, 1)
                        if "contenteditable" in selector:
                            page.keyboard.type(caption, delay=30)
                        else:
                            el.fill(caption)
                        caption_filled = True
                        print(f"  [profile] Caption: {caption[:50]}")
                        break
                except Exception:
                    continue

        human_delay(1, 2)

        # Step 5: Click Share
        shared = False
        for selector in [
            'button:has-text("Share")',
            'div[role="button"]:has-text("Share")',
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn.click()
                    human_delay(8, 12)
                    shared = True
                    print(f"  [profile] Clicked Share")
                    break
            except Exception:
                continue

        if not shared:
            # JS fallback
            try:
                page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('button, div[role="button"]');
                        for (const el of els) {
                            if (el.textContent?.trim() === 'Share' && el.offsetParent !== null) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                human_delay(8, 12)
                shared = True
            except Exception:
                pass

        if shared:
            print(f"  [profile] Post uploaded: {os.path.basename(image_path)}")
            return True
        else:
            print(f"  [profile] Could not click Share button")
            return False

    except Exception as e:
        print(f"  [profile] Error uploading post: {e}")
        return False
