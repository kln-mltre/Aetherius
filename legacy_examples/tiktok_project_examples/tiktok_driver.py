import time
import random
import os
import json
import math
import string 
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR     = Path(__file__).parent.absolute()   
PROJECT_ROOT = BASE_DIR.parent                     
USER_DATA_DIR = os.path.join(BASE_DIR, "tiktok_profile")
DB_FILE       = os.path.join(PROJECT_ROOT, "data", "human_library.json") 

def add_mouse_helper_script(context):
    """
    Injects a script to visually track mouse movements with a red dot overlay for debugging.

    Args:
        context: Playwright browser context.

    Returns:
        None
    """
    context.add_init_script("""
        setInterval(() => {
            const box = document.getElementById('mouse-helper');
            if (!box) {
                const newBox = document.createElement('div');
                newBox.setAttribute('id', 'mouse-helper');
                const style = newBox.style;
                style.width = '20px'; style.height = '20px';
                style.borderRadius = '50%';
                style.background = 'rgba(255, 0, 0, 0.8)';
                style.border = '2px solid white';
                style.position = 'fixed';
                style.zIndex = '2147483647';
                style.pointerEvents = 'none';
                style.transition = 'top 0s linear, left 0s linear';
                document.body.appendChild(newBox);
                window.mouseHelper = newBox;
                document.addEventListener('mousemove', e => {
                    window.mouseHelper.style.left = (e.clientX - 10) + 'px';
                    window.mouseHelper.style.top = (e.clientY - 10) + 'px';
                });
            }
        }, 500);
    """)

def apply_stealth(context):
    """
    Applies stealth scripts to the browser context to minimize bot detection.

    Args:
        context: Playwright browser context.

    Returns:
        None
    """
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) => (
            p.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(p)
        );
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    """)

class BioMouse:
    def __init__(self, page):
        """
        Initializes BioMouse with a Playwright page and a pre-analyzed gesture library.

        Args:
            page: Playwright Page object to control.
        """
        self.page = page
        self.raw_library = self._load_library()
        self.analyzed_library = self._analyze_library(self.raw_library)
        # Start cursor at a random natural position to avoid always originating from (0,0).
        self.current_x = random.randint(400, 800)
        self.current_y = random.randint(300, 600)
        try:
            self.page.mouse.move(self.current_x, self.current_y)
        except: pass

    def _load_library(self):
        """
        Loads the raw gesture library from the JSON file on disk.

        Returns:
            dict: Parsed JSON object containing all recorded gesture data.

        Raises:
            FileNotFoundError: If the gesture library file does not exist.
        """
        if not os.path.exists(DB_FILE):
            raise FileNotFoundError(f"[ERROR] Gesture library not found: '{DB_FILE}'")
        with open(DB_FILE, "r") as f:
            return json.load(f)

    def _downsample_gesture(self, gesture, min_dist=3.0):
        """
        Reduces gesture point density by removing points closer than min_dist pixels.

        Filtering out near-duplicate points reduces command throughput without
        altering the perceived trajectory of the gesture.

        Args:
            gesture: List of (x, y, time) points representing a recorded gesture.
            min_dist: Minimum pixel distance between kept points (default: 3.0).

        Returns:
            List of filtered (x, y, time) points.
        """
        if not gesture or len(gesture) < 3: return gesture

        # Always preserve the first point to keep the trajectory origin intact.
        optimized = [gesture[0]]
        last_x, last_y = gesture[0][0], gesture[0][1]

        # Iterate over intermediate points, skipping those too close to the previous kept point.
        for i in range(1, len(gesture) - 1):
            curr_x, curr_y, curr_t = gesture[i]

            # Euclidean distance from last retained point.
            dist = math.hypot(curr_x - last_x, curr_y - last_y)

            if dist >= min_dist:
                optimized.append(gesture[i])
                last_x, last_y = curr_x, curr_y

        # Always preserve the last point to guarantee the gesture reaches its exact endpoint.
        optimized.append(gesture[-1])
        return optimized

    def _analyze_library(self, library):
        """
        Pre-processes the raw gesture library by downsampling and computing movement vectors.

        Args:
            library: Raw gesture library dict loaded from JSON.

        Returns:
            List of dicts, each containing 'data', 'distance', and 'angle' for a gesture.
        """
        analyzed = []
        for gesture in library["gestures"]:
            if not gesture: continue

            # Downsample at load time so gesture matching is fast at runtime.
            clean_gesture = self._downsample_gesture(gesture, min_dist=3.0)

            end_x, end_y, _ = clean_gesture[-1]
            distance = math.hypot(end_x, end_y)
            angle = math.atan2(end_y, end_x)

            analyzed.append({
                "data": clean_gesture,
                "distance": distance,
                "angle": angle
            })
        return analyzed

    def _get_best_match(self, target_dist, target_angle):
        """
        Finds the recorded gesture that best matches the required distance and angle.

        Searches a random subsample of 50 candidates for performance; a full scan would
        be O(n) on every mouse move and would introduce perceptible latency.

        Args:
            target_dist: Desired movement distance in pixels.
            target_angle: Desired movement angle in radians.

        Returns:
            List of (x, y, time) points for the best-matching gesture.
        """
        best_gesture = None
        best_score = float('inf')
        # Random subsample limits linear search cost while preserving gesture variety.
        candidates = random.sample(self.analyzed_library, min(len(self.analyzed_library), 50))

        for item in candidates:
            dist_score = abs(item["distance"] - target_dist)
            angle_diff = abs(item["angle"] - target_angle)
            # Normalize angle difference to [0, pi] to handle directional wrap-around.
            if angle_diff > math.pi: angle_diff = 2*math.pi - angle_diff

            # Weight angle error heavily (x100) since direction deviation is more visible than distance.
            total_score = dist_score + (angle_diff * 100)

            if total_score < best_score:
                best_score = total_score
                best_gesture = item
        return best_gesture["data"] if best_gesture else random.choice(self.raw_library["gestures"])

    def precise_sleep(self, duration):
        """
        Sleeps for a precise duration, using a busy-wait loop for sub-20ms intervals.

        time.sleep() has OS-level granularity (~10-15ms) that makes it unsuitable for
        sub-millisecond gesture timing. A busy-wait loop is used below the 20ms threshold.

        Args:
            duration: Sleep duration in seconds.

        Returns:
            None
        """
        if duration <= 0: return
        # Use standard sleep for durations above 20ms to avoid wasting CPU unnecessarily.
        if duration > 0.02:
            time.sleep(duration)
            return
        # Busy-wait for sub-20ms precision required by gesture timing.
        end_time = time.perf_counter() + duration
        while time.perf_counter() < end_time:
            pass

    def park_mouse_at_bottom(self):
        """
        Moves the cursor to a random position near the bottom of the viewport.

        Parking the mouse at the bottom is a natural idle behavior that prevents the
        cursor from hovering near interactive elements during upload wait periods.

        Returns:
            None
        """
        try:
            viewport = self.page.evaluate("() => {return {width: window.innerWidth, height: window.innerHeight}}")
            target_x = random.randint(50, viewport['width'] - 50)
            target_y = viewport['height'] - random.randint(20, 50)
            print(f"[INFO] Parking mouse at ({target_x}, {target_y})...")
            self.move_to_coords(target_x, target_y)
        except Exception as e:
            print(f"[WARNING] Park error: {e}")

    def move_to_coords(self, target_x, target_y):
        """
        Moves the cursor to the specified absolute coordinates using a replayed gesture.

        Args:
            target_x: Target X coordinate in pixels.
            target_y: Target Y coordinate in pixels.

        Returns:
            None
        """
        self._replay_gesture(target_x, target_y)

    def move(self, selector):
        """
        Moves the cursor to a random point within the bounding box of a DOM element.

        Targeting a random position within [30%, 70%] of the element bounds avoids
        always clicking the exact center, which is a common bot detection heuristic.

        Args:
            selector: CSS selector string for the target element.

        Returns:
            ElementHandle if found, or None on failure.
        """
        try:
            elem = self.page.wait_for_selector(selector, state="visible", timeout=10000)
            box = elem.bounding_box()
            if not box: return
            # Randomize click target within the center band of the element.
            target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            self._replay_gesture(target_x, target_y)
            return elem
        except Exception as e:
            print(f"[WARNING] Move error: {e}")
            return None

    def _rotate_point(self, x, y, angle_rad):
        """
        Applies a 2D rotation to a point around the origin.

        Args:
            x: X coordinate of the point.
            y: Y coordinate of the point.
            angle_rad: Rotation angle in radians.

        Returns:
            Tuple (new_x, new_y) of the rotated coordinates.
        """
        cos_theta = math.cos(angle_rad)
        sin_theta = math.sin(angle_rad)
        new_x = x * cos_theta - y * sin_theta
        new_y = x * sin_theta + y * cos_theta
        return new_x, new_y

    def _replay_gesture(self, target_x, target_y):
        """
        Replays a recorded gesture geometrically transformed to reach the target coordinates.

        Selects the best-matching gesture from the library, then applies scale and rotation
        to map its original trajectory onto the (start, target) vector. Each point is
        dispatched with its original relative timestamp preserved for realistic timing.

        Args:
            target_x: Destination X coordinate in pixels.
            target_y: Destination Y coordinate in pixels.

        Returns:
            None
        """
        start_x = self.current_x
        start_y = self.current_y
        vec_x = target_x - start_x
        vec_y = target_y - start_y
        target_dist = math.hypot(vec_x, vec_y)
        target_angle = math.atan2(vec_y, vec_x)

        # Skip trivial movements to avoid unnecessary gesture lookup.
        if target_dist < 1: return

        # Select the library gesture closest to the required distance and direction.
        raw_gesture = self._get_best_match(target_dist, target_angle)

        orig_end_x, orig_end_y, _ = raw_gesture[-1]
        orig_dist = math.hypot(orig_end_x, orig_end_y)
        orig_angle = math.atan2(orig_end_y, orig_end_x)

        # Compute scale and rotation needed to align the gesture with the target vector.
        scale = target_dist / orig_dist if orig_dist > 0 else 1
        rotation_needed = target_angle - orig_angle

        # Anchor the timing reference before iterating to preserve inter-point intervals.
        start_time = time.perf_counter()

        for point in raw_gesture:
            p_x, p_y, p_time = point

            # Apply scale then rotation to map the gesture onto the target coordinate space.
            scaled_x = p_x * scale
            scaled_y = p_y * scale
            rotated_x, rotated_y = self._rotate_point(scaled_x, scaled_y, rotation_needed)

            final_x = start_x + rotated_x
            final_y = start_y + rotated_y

            self.page.mouse.move(final_x, final_y)
            self.current_x = final_x
            self.current_y = final_y

            # Respect the original inter-point timing; skip sleep if execution is already behind.
            elapsed = time.perf_counter() - start_time
            sleep_needed = p_time - elapsed
            if sleep_needed > 0:
                self.precise_sleep(sleep_needed)

        # Final correction move to guarantee the cursor lands exactly on the target.
        self.page.mouse.move(target_x, target_y)
        self.current_x = target_x
        self.current_y = target_y

    def click(self, selector):
        """
        Moves to and clicks a DOM element with randomized mouse-down/up timing.

        Args:
            selector: CSS selector string for the target element.

        Returns:
            None
        """
        elem = self.move(selector)
        if elem:
            # Small pre-click pause simulates reaction time after cursor arrival.
            time.sleep(random.uniform(0.05, 0.1))
            self.page.mouse.down()
            # Random hold duration mimics natural click pressure variance.
            time.sleep(random.uniform(0.05, 0.1))
            self.page.mouse.up()

    def type_human(self, selector, text):
        """
        Types text into a field with human-like timing, typos, and per-character delays.

        Args:
            selector: CSS selector string for the target text input.
            text: String to type.

        Returns:
            None
        """
        self.click(selector)
        self.page.keyboard.press("Control+A")
        time.sleep(0.1)
        self.page.keyboard.press("Backspace")

        # Base WPM varies per session to simulate different typing speeds.
        base_speed = random.uniform(0.08, 0.20)

        for char in text:
            # 5% chance of a typo followed by correction to replicate human error patterns.
            if random.random() < 0.05:
                wrong_char = random.choice(string.ascii_lowercase)
                self.page.keyboard.type(wrong_char)
                time.sleep(random.uniform(0.15, 0.4))
                self.page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.1, 0.2))

            self.page.keyboard.type(char)
            current_delay = base_speed + random.uniform(-0.04, 0.05)

            # Spaces take longer as humans briefly pause between words.
            if char == " ": current_delay += random.uniform(0.08, 0.15)
            # Special characters (#, @) require key combination lookup and are typed slower.
            if char in ["#", "@"]: current_delay += random.uniform(0.4, 0.8)
            # Floor delay to 50ms to ensure the DOM registers each keystroke.
            if current_delay < 0.05: current_delay = 0.05

            time.sleep(current_delay)

    def scroll_smooth(self, amount, duration_ms=800):
        """
        Scrolls the page by a given pixel amount over a duration using an ease-out curve.

        Args:
            amount: Total scroll distance in pixels.
            duration_ms: Total scroll duration in milliseconds (default: 800).

        Returns:
            None
        """
        # Step size of ~12ms matches a typical 60fps frame interval for smooth animation.
        steps = int(duration_ms / 12)
        last_offset = 0
        for i in range(1, steps + 1):
            t = i / steps
            # Cubic ease-out: fast start, slow finish — consistent with natural scroll deceleration.
            ease_t = 1 - pow(1 - t, 3)
            current_offset = amount * ease_t
            delta = current_offset - last_offset
            self.page.mouse.wheel(0, delta)
            last_offset = current_offset
            time.sleep(0.012)

    def scroll_down(self):
        """
        Scrolls down a random distance with a random duration for behavioral variety.

        Returns:
            None
        """
        distance = random.randint(300, 700)
        duration = random.randint(600, 1000)
        self.scroll_smooth(distance, duration)

def random_sleep(min_s, max_s, context=""):
    """
    Sleeps for a random duration to simulate human thinking and distraction.

    Args:
        min_s: Minimum seconds to sleep.
        max_s: Maximum seconds to sleep.
        context: Optional string describing the sleep context.

    Returns:
        None
    """
    duration = random.uniform(min_s, max_s)
    # Occasionally (10%), add extra delay to simulate human distraction.
    if random.random() < 0.1:
        duration += random.uniform(1.5, 4.0)
        print(f"   [BUSY] (Distraction...) +{duration:.2f}s")
    time.sleep(duration)

def upload_video_playwright(video_path, description, dry_run=False):
    """
    Automates the upload of a video to TikTok Studio using Playwright and human-like interaction.

    Args:
        video_path: Path to the video file.
        description: Description text to post.
        dry_run: If True, simulates the upload without clicking 'Post'.

    Returns:
        Tuple (success: bool, error_message: str or None)
    """
    print(f"[INFO] Starting upload sequence (Organic Timing & Official Chrome)...")

    if not os.path.exists(USER_DATA_DIR): return False, "Profile missing"

    with sync_playwright() as p:
        # CONFIGURATION 0.9 (Best config)
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

        apply_stealth(context)
        add_mouse_helper_script(context)

        page = context.pages[0]

        try:
            bio = BioMouse(page)

            target_url = "https://www.tiktok.com/tiktokstudio/upload?lang=fr"
            print(f"[INFO] Navigating to upload page...")
            page.goto(target_url)

            # Human waits before interacting with the page.
            random_sleep(3.5, 6.0, "Page load")

            # Mouse movement for realism (re-centering).
            bio.move_to_coords(random.randint(300, 600), random.randint(300, 500))
            random_sleep(1.0, 2.0)

            print("[INFO] Selecting file...")
            if not os.path.isfile(video_path): return False, "Video not found"

            # Simulate searching for upload button before triggering input.
            try:
                bio.move("div[class*='upload'], div[class*='container']")
                random_sleep(0.5, 1.5, "Before file open")
            except: pass

            page.set_input_files('input[type="file"]', os.path.abspath(video_path))

            # Human waits after upload before typing description.
            print("[INFO] Upload in progress...")
            random_sleep(2.0, 5.0, "Post-upload wait")

            try:
                page.wait_for_selector("div[contenteditable='true'], textarea", timeout=60000)
                print("[INFO] Writing description...")

                bio.click("div[contenteditable='true'], textarea")
                random_sleep(0.5, 1.5, "Text field focus")

                bio.type_human("div[contenteditable='true'], textarea", description + " ")

                # Human re-reads description before posting.
                random_sleep(2.0, 4.5, "Description review")

            except Exception as e:
                print(f"[WARNING] Description: {e}")

            print("[INFO] Parking mouse (waiting for upload to finish)...")
            bio.park_mouse_at_bottom()

            print("[INFO] Waiting for 'Post' button...")
            post_btn = page.locator("button:has-text('Publier'), button:has-text('Post')").first

            found_and_visible = False
            # Check regularly for button visibility.
            for i in range(40):
                if post_btn.is_visible():
                    box = post_btn.bounding_box()
                    viewport_height = page.viewport_size['height'] if page.viewport_size else 900

                    if box and box['y'] < viewport_height:
                        if not post_btn.get_attribute("disabled"):
                            print("[OK] Active 'Post' button detected.")
                            found_and_visible = True
                            break
                        else:
                            print("   [BUSY] Upload in progress (button disabled)...")
                            random_sleep(1.5, 3.0, "Active wait")
                            continue

                print(f"   [INFO] Scrolling to search for button...")
                bio.scroll_down()
                random_sleep(1.0, 2.5, "Between scrolls")

            if found_and_visible:
                # Human hesitation before final click.
                print("[INFO] Hesitating before final click...")

                bio.move("button:has-text('Publier')")
                random_sleep(0.8, 1.8, "Hover button")

                if dry_run:
                    print("\n[INFO] DRY RUN: Not clicking.")
                    time.sleep(3)
                    return True, "DRY RUN OK"
                else:
                    print("[INFO] FINAL CLICK!")
                    bio.click("button:has-text('Publier')")

                    print("[INFO] Waiting for TikTok confirmation notification...")
                    try:
                        # Use regex to match multiple success message variants (case-insensitive).
                        success_locator = page.locator("text=/Vidéo publiée|publications|j'aime/i").first
                        success_locator.wait_for(state="visible", timeout=35000)

                        print("[SUCCESS] Upload succeeded (notification detected)")
                        random_sleep(3, 5, "Success contemplation")
                        return True, None

                    except Exception as e:
                        print(f"[ERROR] Success notification never appeared.")
                        debug_img = os.path.join(BASE_DIR, f"debug_error_{int(time.time())}.png")
                        page.screenshot(path=debug_img)
                        print(f"[INFO] Error screenshot saved: {debug_img}")
                        return False, "Success notification not detected. See screenshot."

            else:
                return False, "Post button not found or disabled (timeout)"

        except Exception as e:
            return False, str(e)
        finally:
            context.close()

def test_bot_score():
    """
    Runs a bot detection test using mouse movements and recaptcha score analysis.

    Returns:
        None
    """
    print("[INFO] Starting BOT DETECTION TEST...")

    with sync_playwright() as p:
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

        apply_stealth(context)
        page = context.pages[0]
        bio = BioMouse(page)

        # Mouse movement test for recaptcha.
        print("[INFO] Connecting to Antcpt (Mouse Test)...")
        page.goto("https://antcpt.com/score_detector/")
        time.sleep(1)

        print("[INFO] Moving mouse to prove human behavior...")
        for _ in range(5):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            bio.move_to_coords(x, y)
            time.sleep(random.uniform(0.5, 1.0))

        print("[INFO] Analyzing score...")
        time.sleep(3)

        try:
            score = page.evaluate("document.body.innerText")
            if "Score: 0.9" in score:
                print("\n[OK] SCORE 0.9 - Perfectly human!")
            elif "Score: 0.7" in score:
                print("\n[OK] SCORE 0.7 - Probably human.")
            elif "Score: 0.3" in score:
                print("\n[WARNING] SCORE 0.3 - Suspect (strange movements).")
            else:
                print(f"\n[INFO] Raw result: Check the screen!")
        except:
            print("Check the screen to see your score.")

        time.sleep(30)
        context.close()

if __name__ == "__main__":
    test_bot_score()