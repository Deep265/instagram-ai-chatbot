from dotenv.main import logger
import os
import time
import random
import json
import pickle
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instagram_cookies.pkl')

class InstagramEngine:
    def __init__(self, logger, username, password):
        self.logger = logger
        self.username = username
        self.password = password
        self.driver = None
        self.tabs = {}  # {thread_name: window_handle}
        self.thread_urls = {} # {thread_name: canonical_url}
        self.main_handle = None
        self.full_name = "Nyra" # Default if not set

    def start(self, headless=False):
        self.logger.info("Initializing undetected-chromedriver...")
        options = uc.ChromeOptions()
        if headless:
            options.add_argument('--headless=new')

        # Persistent session folder
        user_data_dir = os.path.join(os.getcwd(), 'chrome_session')
        os.makedirs(user_data_dir, exist_ok=True)
        options.add_argument(f'--user-data-dir={user_data_dir}')

        # Suppress notifications & noise
        options.add_argument('--log-level=3')
        options.add_argument('--disable-blink-features=AutomationControlled')
        prefs = {"profile.default_content_setting_values.notifications": 2}
        options.add_experimental_option("prefs", prefs)

        self.driver = uc.Chrome(options=options)
        self.driver.set_window_size(1280, 800)
        self.main_handle = self.driver.current_window_handle
        self.logger.info(f"Browser started (headless={headless})")

    def stop(self):
        """Closes the browser."""
        try:
            if self.driver:
                self.save_cookies()
                self.driver.quit()
        except Exception:
            pass

    def save_cookies(self):
        """Save browser cookies to disk for session persistence."""
        try:
            cookies = self.driver.get_cookies()
            with open(COOKIES_FILE, 'wb') as f:
                pickle.dump(cookies, f)
            self.logger.info(f"Saved {len(cookies)} cookies to {COOKIES_FILE}")
        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")

    def load_cookies(self):
        """Load cookies from disk and inject into browser."""
        if not os.path.exists(COOKIES_FILE):
            return False
        try:
            with open(COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
            self.driver.get('https://www.instagram.com/')
            time.sleep(2)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            self.logger.info(f"Loaded {len(cookies)} cookies from disk.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load cookies: {e}")
            return False

    def _human_type(self, element, text):
        """Types text character by character with random delays to mimic a human."""
        element.click()
        time.sleep(0.3)
        element.clear()
        time.sleep(0.2)
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.03, 0.12))

    def _check_security_challenges(self):
        """Pauses the script if Instagram asks for 2FA or verification."""
        challenge_indicators = [
            "verify", "security code", "confirm your",
            "suspicious", "challenge", "checkpoint",
            "we detected an unusual", "enter the code"
        ]
        page_text = self.driver.page_source.lower()
        current_url = self.driver.current_url.lower()
        
        is_challenge = any(indicator in page_text for indicator in challenge_indicators)
        is_challenge = is_challenge or "challenge" in current_url or "checkpoint" in current_url
        
        if is_challenge:
            print("\n" + "=" * 50)
            print("🛑 SECURITY CHALLENGE DETECTED!")
            print("Instagram is asking for verification.")
            print("Please check the browser window and complete the challenge.")
            print("=" * 50)
            input(">> Press Enter after you have resolved it... ")
            time.sleep(3)
            # Save cookies immediately after resolving the challenge
            self.save_cookies()
            print()

    def handle_popups(self):
        """Click through common Instagram popups after login."""
        # First, try to SAVE login info (this helps session persistence)
        save_texts = ["Save Info", "Save Your Login Info", "Save your login info"]
        for text in save_texts:
            try:
                btns = self.driver.find_elements(
                    By.XPATH,
                    f"//button[contains(text(), '{text}')]"
                )
                if btns:
                    btns[0].click()
                    self.logger.info(f"Clicked: '{text}' to save session")
                    time.sleep(2)
                    break
            except Exception:
                pass

        # Then dismiss other popups
        dismiss_texts = ["Not Now", "Turn On", "Cancel"]
        for _ in range(3):
            for text in dismiss_texts:
                try:
                    btns = self.driver.find_elements(
                        By.XPATH,
                        f"//button[contains(text(), '{text}')]"
                    )
                    if btns:
                        btns[0].click()
                        self.logger.info(f"Dismissed popup: '{text}'")
                        time.sleep(2)
                except Exception:
                    pass
            time.sleep(1)

    def login(self, session_id=None):
        """Login to Instagram. Uses persistent session if available."""
        
        # Try loading saved cookies first
        if os.path.exists(COOKIES_FILE):
            self.logger.info("Found saved cookies, attempting session restore...")
            self.load_cookies()
            self.driver.get('https://www.instagram.com/')
            time.sleep(5)
        else:
            self.logger.info("No saved cookies found. Navigating to Instagram...")
            self.driver.get('https://www.instagram.com/')
            time.sleep(5)

        # Check if already logged in via persistent session
        current_url = self.driver.current_url
        try:
            home_icons = self.driver.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Home"]')
            direct_icons = self.driver.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Direct"]')
            msg_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href="/direct/inbox/"]')
            if home_icons or direct_icons or msg_links or "direct/inbox" in current_url:
                self.logger.info("Already logged in (session detected)!")
                return True
        except Exception:
            pass

        # Not logged in — navigate to login page
        self.logger.info("Not logged in. Navigating to login page...")
        self.driver.get('https://www.instagram.com/accounts/login/')
        time.sleep(5)

        # Dismiss cookie banners if present
        try:
            cookie_btns = self.driver.find_elements(
                By.XPATH,
                '//button[contains(text(), "Allow") or contains(text(), "Accept") or contains(text(), "cookie")]'
            )
            if cookie_btns:
                cookie_btns[0].click()
                time.sleep(2)
        except Exception:
            pass

        try:
            # ============================================================
            # CRITICAL: Instagram uses name="email" and name="pass"
            # NOT name="username" and name="password" as commonly assumed!
            # ============================================================
            self.logger.info("Waiting for login form to appear...")
            
            # Wait for element to be CLICKABLE, not just present
            username_input = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="email"]'))
            )
            password_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="pass"]'))
            )

            self.logger.info("Login form found! Typing credentials...")

            # Use JavaScript to focus + ActionChains to type (bypasses 'not interactable')
            self.driver.execute_script("arguments[0].focus(); arguments[0].click();", username_input)
            time.sleep(0.5)
            username_input.clear()
            time.sleep(0.3)
            ActionChains(self.driver).move_to_element(username_input).click().perform()
            time.sleep(0.3)
            for char in self.username:
                username_input.send_keys(char)
                time.sleep(random.uniform(0.03, 0.12))
            
            time.sleep(0.5)

            self.driver.execute_script("arguments[0].focus(); arguments[0].click();", password_input)
            time.sleep(0.5)
            password_input.clear()
            time.sleep(0.3)
            ActionChains(self.driver).move_to_element(password_input).click().perform()
            time.sleep(0.3)
            for char in self.password:
                password_input.send_keys(char)
                time.sleep(random.uniform(0.03, 0.12))

            time.sleep(1)

            # Click the Log In button
            login_btn = self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
            self.driver.execute_script("arguments[0].click();", login_btn)

            self.logger.info("Waiting for login to complete...")
            time.sleep(10)

            # Check for security challenges
            self._check_security_challenges()

            # Handle popups (Save Info, Notifications, etc.)
            self.handle_popups()

            # Verify login success
            current_url = self.driver.current_url
            home_icons = self.driver.find_elements(By.CSS_SELECTOR, 'svg[aria-label="Home"]')
            if "login" not in current_url or home_icons:
                self.logger.info("✅ Login successful!")
                self.save_cookies()  # Save session for next run
                return True
            else:
                self.logger.error("Login failed — still on login page.")
                return False

        except Exception as e:
            self.logger.error(f"Login error: {e}")
            # Last resort: check if we somehow logged in despite the error
            try:
                if "login" not in self.driver.current_url:
                    self.logger.info("Login appears successful despite error.")
                    return True
            except Exception:
                pass
            return False

    def navigate_to_inbox(self):
        """Navigate to the DM inbox."""
        self.logger.info("Navigating to inbox...")
        self.driver.get('https://www.instagram.com/direct/inbox/')
        time.sleep(5)
        self.handle_popups()
        self.logger.info("Inbox loaded.")

    def get_recent_threads(self, amount=10):
        """Scrapes the inbox for recent conversation threads."""

        # Ensure we are on the main handle
        if self.main_handle and self.driver.current_window_handle != self.main_handle:
            self.driver.switch_to.window(self.main_handle)

        if "direct/inbox" not in self.driver.current_url:
            self.driver.get('https://www.instagram.com/direct/inbox/')
            time.sleep(4)

        threads = []
        try:
            # Instagram renders each conversation as a div[role="button"] in the sidebar.
            # Rows that contain a middle-dot '·' are conversation previews (timestamp separator).
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
            elements = [b for b in buttons if '·' in b.text and any(x in b.text for x in ['m', 'h', 'd', 'w', 's'])]

            for el in elements[:amount]:
                try:
                    text = el.text.strip()
                    name_text = text.split('\n')[0].strip()

                    # FIX: Only mark as unread when Instagram explicitly says "Unread"
                    # The old logic flagged almost every thread as unread
                    is_unread = "Unread" in text

                    threads.append({
                        "name": name_text,
                        "is_unread": is_unread,
                        "element": el
                    })
                except Exception:
                    continue

        except Exception as e:
            self.logger.error(f"Error fetching threads: {e}")
        
        logger.info(f"Recent Threads Output : {threads}")
        return threads

    def ensure_thread_tab(self, thread_name, element):
        """Opens a thread in a new tab if not already open, or switches to it."""
        if thread_name in self.tabs:
            try:
                handle = self.tabs[thread_name]
                if handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    logger.info(f"Thread tab open successfull for {thread_name}")
                    return True
                else:
                    logger.info(f"Thread tab not found for {thread_name}")
                    del self.tabs[thread_name]
            except Exception:
                if thread_name in self.tabs:
                    logger.info(f"Exception in thread tab for {thread_name}")
                    del self.tabs[thread_name]

        # Limit to 5 worker tabs
        if len(self.tabs) >= 5:
            return False

        self.logger.info(f"Attempting to open worker tab for: {thread_name}")
        try:
            # 1. Capture current inbox location to return later
            inbox_url = self.driver.current_url

            # 2. Click the chat row normally to navigate there in the main tab
            self.logger.info(f"Clicking thread for {thread_name} to capture URL...")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            
            # Use JS click for speed and to avoid overlays
            self.driver.execute_script("arguments[0].click();", element)
            
            # 3. Wait for the URL to change to a thread URL (.../direct/t/...)
            thread_url = None
            for _ in range(15): # Max 7.5 seconds wait
                current_url = self.driver.current_url
                if "/direct/t/" in current_url:
                    thread_url = current_url
                    break
                time.sleep(0.5)
            
            if not thread_url:
                self.logger.error(f"Failed to capture thread URL for {thread_name} after click.")
                # Return to inbox if stuck
                self.driver.get(inbox_url)
                return False

            self.logger.info(f"Captured thread URL: {thread_url}")

            # 4. Open this specific thread URL in a NEW tab/window
            self.driver.execute_script(f"window.open('{thread_url}', '_blank');")
            time.sleep(2)
            
            handles = self.driver.window_handles
            new_handle = handles[-1]
            self.tabs[thread_name] = new_handle
            self.thread_urls[thread_name] = thread_url # Store recorded URL
            
            # 5. Return the MAIN tab to the inbox so it can monitor other chats
            self.logger.info("Returning main tab to inbox overview...")
            self.driver.switch_to.window(self.main_handle)
            self.driver.get("https://www.instagram.com/direct/inbox/")
            time.sleep(1)
            
            return True

        except Exception as e:
            self.logger.error(f"Error in Click-and-Capture for {thread_name}: {e}")
            try: self.driver.switch_to.window(self.main_handle)
            except: pass
            
        return False

    def close_thread_tab(self, thread_name):
        """Closes the tab for a thread and returns to main."""
        try:
            if thread_name in self.tabs:
                handle = self.tabs[thread_name]
                if handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
                if thread_name in self.tabs: del self.tabs[thread_name]
                if thread_name in self.thread_urls: del self.thread_urls[thread_name]
        except Exception:
            pass
        finally:
            try:
                if self.main_handle in self.driver.window_handles:
                    self.driver.switch_to.window(self.main_handle)
            except: pass

    def get_messages(self, url, limit=10):
        """
        Reads recent messages using JavaScript DOM extraction.

        HOW ROLE DETECTION WORKS (learned from live DOM inspection):
        - The chat panel is a narrow column. ALL messages sit between left~357-550px.
          A viewport-midpoint (640px) misclassifies everything as incoming.
        - Fix: auto-detect the panel center from min/max left of all candidate nodes,
          then use that as the split point. right of panel-center = you, left = them.
        - Sidebar exclusion: sidebar items sit at left < 200px. We skip those entirely.
        - Every message appears as both SPAN (leaf) and DIV (wrapper). We pick the leaf
          by skipping any node whose child [dir=auto] has the same innerText.
        """
        import re

        current_url = self.driver.current_url.split("?")[0].rstrip("/")
        target_url = url.split("?")[0].rstrip("/")

        if current_url != target_url:
            self.logger.info(f"Navigating to thread: {url}")
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'div[contenteditable="true"], textarea')
                    )
                )
            except Exception:
                time.sleep(5)

        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        messages = []
        try:
            raw = self.driver.execute_script("""
                var candidates = [];
                var allDirAuto = Array.from(document.querySelectorAll("[dir=auto]"));

                allDirAuto.forEach(function(node) {
                    var text = (node.innerText || "").trim();
                    if (!text || text.length < 2) return;

                    var rect = node.getBoundingClientRect();
                    if (rect.height === 0 || rect.width === 0) return;

                    // SIDEBAR/HEADER EXCLUSION: Skip everything on far left (Sidebar)
                    // Thread content starts at ~300px+
                    if (rect.left < 300) return;

                    // Skip wrapper divs: if any child [dir=auto] has the exact same text,
                    // this node is just a container — skip it, we will pick the child.
                    var children = node.querySelectorAll("[dir=auto]");
                    var isWrapper = false;
                    for (var i = 0; i < children.length; i++) {
                        if ((children[i].innerText || "").trim() === text) {
                            isWrapper = true;
                            break;
                        }
                    }
                    if (isWrapper) return;

                    // CLASS-BASED ROLE DETECTION
                    // Instagram usually wraps outgoing (assistant) messages in classes like 'x6s0dn4'
                    // and incoming (user) in 'x78zum5' or similar.
                    var role = "user";
                    var parent = node.closest('div[class]');
                    if (parent) {
                        var cls = parent.className || "";
                        // x6s0dn4 is a common right-aligned container class
                        if (cls.includes("x6s0dn4")) role = "assistant";
                        else if (cls.includes("x78zum5")) role = "user";
                    }

                    candidates.push({ text: text, left: rect.left, top: rect.top, role: role });
                });

                if (candidates.length === 0) return [];

                // PANEL MIDPOINT for cases where classes aren't clear
                var lefts = candidates.map(function(c) { return c.left; });
                var minLeft = Math.min.apply(null, lefts);
                var maxLeft = Math.max.apply(null, lefts);
                var panelMid = (minLeft + maxLeft) / 2 + 50;

                var results = candidates.map(function(c) {
                    var finalRole = c.role;
                    // If class-based detection is ambiguous, use position fallback
                    if (finalRole === "user" && c.left >= panelMid) finalRole = "assistant";
                    
                    return {
                        text: c.text,
                        role: finalRole,
                        top: c.top,
                        left: c.left
                    };
                });

                results.sort(function(a, b) { return a.top - b.top; });
                return results;
            """)

            logger.info(f"RAW Message Output : {raw}")

            if not raw:
                self.logger.warning("JS extraction returned no elements.")
                return []

            lefts = [r["left"] for r in raw]
            panel_mid_used = (min(lefts) + max(lefts)) / 2 + 30
            self.logger.info(
                f"Panel left range: {min(lefts):.0f}-{max(lefts):.0f}px | "
                f"split at: {panel_mid_used:.0f}px"
            )

            # --- NOISE FILTERS ---
            NOISE_EXACT = {
                "today", "yesterday", "seen", "delivered", "active now",
                "send message", "message", "send", "new message", "note",
                "primary", "general", "requests", "your note",
                "your messages", "send private photos and messages to a friend or group.",
                "send a message to start a chat", "active"
            }
            TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}\s*(am|pm)?$", re.IGNORECASE)
            DAY_TIME_RE = re.compile(
                r"^(mon|tue|wed|thu|fri|sat|sun)\s+\d{1,2}:\d{2}", re.IGNORECASE
            )
            DATE_RE = re.compile(
                r"^(january|february|march|april|may|june|july|august|"
                r"september|october|november|december|\d{1,2}/\d{1,2})",
                re.IGNORECASE
            )
            DURATION_RE = re.compile(r"^\d{1,2}[mhdw]$", re.IGNORECASE)

            for item in raw:
                text = item["text"].strip()
                role = item["role"]

                # Detailed filtering
                if not text or len(text) < 1:
                    continue
                if "·" in text:
                    continue
                if text.lower() in NOISE_EXACT:
                    continue
                
                # Exclude profile headers/usernames (Deepak Chaudhari, deepakchaudhari265, etc.)
                if text == self.username or (hasattr(self, 'full_name') and text == self.full_name):
                    continue

                if TIMESTAMP_RE.match(text) or DAY_TIME_RE.match(text) or DATE_RE.match(text) or DURATION_RE.match(text):
                    continue

                # NOTE: We allow duplicates (Hi, Hello) to preserve conversation flow.
                messages.append({"role": role, "content": text})

            # Check if history is JUST landing page garbage - if so return empty to wait
            if len(messages) == 0:
                self.logger.debug("Chat is currently showing empty-state landing page.")

            self.logger.info(f"Read {len(messages)} unique message items from thread.")
            return messages[-limit:]

        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}")

        return messages

    def send_message(self, url, text):
        """Sends a message to the specified thread."""
        self.logger.info(f"Sending message to {url}...")
        
        # Don't try to send messages to the generic inbox URL!
        if "/direct/t/" not in url:
            self.logger.error(f"Cannot send message to non-thread URL: {url}")
            return False

        # Ensure we are on the correct thread URL
        if self.driver.current_url.split('?')[0].rstrip('/') != url.split('?')[0].rstrip('/'):
            self.driver.get(url)
            time.sleep(4)

        try:
            # Expanded selector list for the message input field (updated for latest UI)
            selectors = [
                (By.CSS_SELECTOR, "div[role='textbox'][aria-label*='Message']"),
                (By.CSS_SELECTOR, 'textarea[aria-label="Message"]'),
                (By.CSS_SELECTOR, 'div[aria-label="Message"]'),
                (By.CSS_SELECTOR, 'div[contenteditable="true"]'),
                (By.XPATH, "//div[@role='textbox' and @aria-label='Message']"),
                (By.XPATH, "//textarea[@aria-label='Message']"),
                (By.CSS_SELECTOR, "div[role='textbox']"),
                (By.XPATH, "//textarea[@role='textbox']"),
            ]

            box = None
            for by, sel in selectors:
                try:
                    elements = self.driver.find_elements(by, sel)
                    if elements:
                        box = elements[0]
                        self.logger.debug(f"Found message input using selector {sel} ({by})")
                        break
                except Exception as e:
                    self.logger.debug(f"Selector {sel} ({by}) raised {e}")
                    continue

            if not box:
                self.logger.error("Could not locate the message input box with any selector.")
                return False

            # Focus the input box
            self.driver.execute_script("arguments[0].focus();", box)
            time.sleep(0.2)

            # --- EMOJI-SAFE TYING ---
            # ChromeDriver's send_keys fails for non-BMP characters like emojis.
            # We use JS execCommand to insert text directly into the contenteditable div.
            self.driver.execute_script("""
                var el = arguments[0];
                var text = arguments[1];
                el.innerText = ''; // Clear first
                // Use execCommand to preserve Instagram's internal state
                if (document.queryCommandSupported('insertText')) {
                    document.execCommand('insertText', false, text);
                } else {
                    el.innerText = text;
                }
                // Trigger input events so the 'Send' button activates
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            """, box, text)
            
            time.sleep(1)
            box.send_keys(Keys.ENTER)
            # Wait for the message bubble to appear (basic verification)
            time.sleep(2)
            self.logger.info("Message sent successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    def print_inbox_summary(self, max_threads=10, messages_per_thread=10):
        """Fetch all inbox threads and print messages per user in the terminal."""
        print("\n" + "=" * 60)
        print("📬 INSTAGRAM INBOX SUMMARY")
        print("=" * 60)

        if self.main_handle and self.driver.current_window_handle != self.main_handle:
            self.driver.switch_to.window(self.main_handle)

        threads = self.get_recent_threads(amount=max_threads)

        if not threads:
            print("  No threads found in inbox.")
            print("=" * 60)
            return

        for i, thread in enumerate(threads, 1):
            name = thread['name']
            print(f"\n{'─' * 60}")
            print(f"  💬 Chat #{i}: {name}")
            print(f"     Status: {'Unread 🔵' if thread['is_unread'] else 'Read'}")
            print(f"{'─' * 60}")

            try:
                current_btns = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    'div[role="listbox"] div[role="button"], div[role="list"] div[role="button"]'
                )
                if not current_btns:
                    current_btns = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')

                target_btn = None
                for btn in current_btns:
                    first_line = btn.text.strip().split('\n')[0].strip()
                    if first_line == name:
                        target_btn = btn
                        break

                if target_btn:
                    self.driver.execute_script("arguments[0].click();", target_btn)
                    # Wait for the chat input to appear — confirms the thread is loaded
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, 'div[contenteditable="true"], textarea')
                            )
                        )
                    except Exception:
                        time.sleep(5)

                    # FIX: pass messages_per_thread as the limit so we actually get that many
                    messages = self.get_messages(self.driver.current_url, limit=messages_per_thread)
                    if not messages:
                        print("     (No messages found yet or unable to parse DOM)")
                    else:
                        for msg in messages:
                            sender_icon = "🤖 You" if msg['role'] == 'assistant' else "👤 Them"
                            print(f"     {sender_icon}: {msg['content']}")
                else:
                    print(f"     (Could not find thread button for '{name}')")

                # Navigate back to inbox
                self.driver.get('https://www.instagram.com/direct/inbox/')
                time.sleep(3)

            except Exception as e:
                print(f"     (Error reading messages: {e})")

        print(f"\n{'=' * 60}")
        print(f"  Total threads displayed: {len(threads)}")
        print("=" * 60 + "\n")