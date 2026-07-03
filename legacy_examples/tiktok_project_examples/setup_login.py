import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent.absolute()
# Can 'continue' a session by reusing the same user_data_dir, which stores cookies and local storage.
USER_DATA_DIR = os.path.join(BASE_DIR, "tiktok_profile")

def login_manual():
    """
    Launches a persistent Chrome browser session for manual TikTok login and profile capture.

    The browser is launched in 'stealth' mode with custom arguments to maximize compatibility
    and minimize detection. User is instructed to log in, accept cookies, browse for 30 seconds,
    and close the window manually to save the profile.

    Returns:
        None
    """
    print("[INFO] Secure login mode activated.")
    print("The browser will open with 'Stealth' parameters.")
    print("1. Log in to TikTok (and Google for score boost if desired).")
    print("2. Accept cookies.")
    print("3. Browse for 30 seconds.")
    print("4. Close the window manually to save your profile.")

    with sync_playwright() as p:
        # Launch Chrome with persistent context for profile capture.
        # 'user_data_dir' ensures profile is saved for future bot sessions.
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            executable_path="/usr/bin/google-chrome",
            channel="chrome",
            headless=False,
            viewport=None,
            ignore_default_args=["--enable-automation", "--no-sandbox"],
            args=[
                "--start-maximized",
                "--disable-infobars"
            ]
        )

        page = context.pages[0]
        page.goto("https://www.google.com/")

        # Wait for user to close the window manually; timeout is intentionally very large.
        try:
            page.wait_for_timeout(99999999)
        except:
            print("[SUCCESS] Profile saved.")

if __name__ == "__main__":
    login_manual()