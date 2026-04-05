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
        self.tabs = {}  # {thread_id: window_handle}
        self.main_handle = None

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
        """Scrapes the inbox for recent conversation threads and detects unread status."""
        
        # Ensure we are on the main handle
        if self.main_handle and self.driver.current_window_handle != self.main_handle:
            self.driver.switch_to.window(self.main_handle)
            
        if "direct/inbox" not in self.driver.current_url:
            self.driver.get('https://www.instagram.com/direct/inbox/')
            time.sleep(4)

        threads = []
        try:
            # Find all buttons in Sidebar
            buttons = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
            # Elements containing middle-dot '·' are thread rows
            elements = [b for b in buttons if '·' in b.text and any(x in b.text for x in ['m', 'h', 'd', 'w'])]

            for el in elements[:amount]:
                try:
                    text = el.text.strip()
                    name_text = text.split('\n')[0]
                    
                    # Instagram uses Unread text or specific bold patterns for new messages
                    # We also check if the last activity was not us sending an attachment/message
                    is_unread = "Unread" in text or ("sent" not in text.lower() and "Reacted" not in text and "You:" not in text)
                    
                    threads.append({
                        "name": name_text,
                        "is_unread": is_unread,
                        "element": el
                    })
                except Exception:
                    continue

        except Exception as e:
            self.logger.error(f"Error fetching threads: {e}")
        return threads

    def ensure_thread_tab(self, thread_name, element):
        """Opens a thread in a new tab if not already open, or switches to it."""
        if thread_name in self.tabs:
            try:
                handle = self.tabs[thread_name]
                if handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    return True
                else:
                    del self.tabs[thread_name]
            except Exception:
                if thread_name in self.tabs:
                    del self.tabs[thread_name]

        # Limit to 5 worker tabs
        if len(self.tabs) >= 5:
            return False

        self.logger.info(f"Opening worker tab for: {thread_name}")
        try:
            # Scroll to element to ensure it's interactable
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)

            # Try to get the URL from the parent <a> tag if it exists
            # Instagram often wraps these buttons in an <a> tag
            try:
                link_el = element.find_element(By.XPATH, "./ancestor::a")
                thread_url = link_el.get_attribute("href")
                if thread_url:
                    self.driver.execute_script(f"window.open('{thread_url}', '_blank');")
                    time.sleep(2)
                    handles = self.driver.window_handles
                    new_handle = handles[-1]
                    self.tabs[thread_name] = new_handle
                    self.driver.switch_to.window(new_handle)
                    return True
            except Exception:
                pass

            # Fallback to Control+Click if URL extraction fails
            ActionChains(self.driver).key_down(Keys.CONTROL).click(element).key_up(Keys.CONTROL).perform()
            time.sleep(3)
            
            handles = self.driver.window_handles
            if len(handles) > len(self.tabs) + 1:
                new_handle = handles[-1]
                self.tabs[thread_name] = new_handle
                self.driver.switch_to.window(new_handle)
                return True
            
        except Exception as e:
            self.logger.error(f"Failed to open tab for {thread_name}: {e}")
            
        return False

    def close_thread_tab(self, thread_name):
        """Closes the tab for a thread and returns to main."""
        try:
            if thread_name in self.tabs:
                handle = self.tabs[thread_name]
                if handle in self.driver.window_handles:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
                del self.tabs[thread_name]
        except Exception:
            pass
        finally:
            try:
                if self.main_handle in self.driver.window_handles:
                    self.driver.switch_to.window(self.main_handle)
            except: pass

    def get_messages(self, url, limit=5):
        """Reads recent messages from the current thread (no refresh if already there)."""
        # Normalize URLs for comparison (strip trailing slashes)
        current_url = self.driver.current_url.rstrip('/')
        target_url = url.split('?')[0].rstrip('/')  # Ignore query params

        if current_url != target_url:
            self.logger.info(f"Navigating to thread: {url}")
            self.driver.get(url)
            time.sleep(4)

        messages = []
        try:
            # Broader search for message bubbles
            msg_els = self.driver.find_elements(By.CSS_SELECTOR, 'main span, div[dir="auto"]')
            
            seen_texts = set()
            for el in msg_els:
                try:
                    text = el.text.strip()
                    # Skip noise: timestamps, single letters, or empty strings
                    if not text or len(text) < 1 or '·' in text or text in seen_texts:
                        continue
                    
                    # More resilient Role Detection
                    role = "user" # Default to user
                    
                    # 1. Check for manual prefix if present in some views
                    if text.startswith("You:"):
                        role = "assistant"
                        text = text.replace("You:", "").strip()
                    else:
                        # 2. Check for alignment or authorship via parent element class/style
                        try:
                            # Higher level container often has classes like 'xexx8yu' or styles
                            container = el.find_element(By.XPATH, "./ancestor::div[contains(@class, ' ') or @style][1]")
                            style = container.get_attribute("style") or ""
                            classes = container.get_attribute("class") or ""
                            
                            if "flex-end" in style or "x6s0dn4" in classes: # Common alignment indicators
                                role = "assistant"
                            elif "flex-start" in style or "x78zum5" in classes:
                                role = "user"
                            else:
                                # 3. Fallback: Check for profile picture link (usually present for incoming)
                                is_incoming = container.find_elements(By.XPATH, ".//img") or el.find_elements(By.XPATH, "./ancestor::div[1]//img")
                                role = "user" if is_incoming else "assistant"
                        except Exception:
                            pass

                    # Avoid adding identical consecutive messages
                    messages.append({"role": role, "content": text})
                    seen_texts.add(text)
                except Exception:
                    continue

            # self.logger.info(f"Read {len(messages)} unique messages from {target_url}")
            return messages[-limit:]
        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}")

        return messages

    def send_message(self, url, text):
        """Sends a message to the specified thread."""
        self.logger.info(f"Sending message to {url}...")
        if self.driver.current_url != url:
            self.driver.get(url)
            time.sleep(4)

        try:
            # Find the message input box
            selectors = [
                (By.CSS_SELECTOR, 'div[aria-label="Message"]'),
                (By.CSS_SELECTOR, 'div[contenteditable="true"]'),
                (By.XPATH, "//div[@role='textbox' and @aria-label='Message']")
            ]
            
            box = None
            for by, sel in selectors:
                try:
                    elements = self.driver.find_elements(by, sel)
                    if elements:
                        box = elements[0]
                        break
                except Exception:
                    continue

            if box:
                # Human-like interaction: focus, click, type
                self.driver.execute_script("arguments[0].focus(); arguments[0].click();", box)
                time.sleep(0.5)
                ActionChains(self.driver).move_to_element(box).click().perform()
                time.sleep(0.5)
                
                # Type human-like
                for char in text:
                    box.send_keys(char)
                    time.sleep(random.uniform(0.04, 0.15))
                
                time.sleep(0.5)
                box.send_keys(Keys.ENTER)
                time.sleep(2)
                self.logger.info("Message sent successfully.")
                return True
            else:
                self.logger.error("Could not find message input box.")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
        return False

    def print_inbox_summary(self, max_threads=10, messages_per_thread=10):
        """Fetch all inbox threads and print messages per user in the terminal (sequential for stability)."""
        print("\n" + "=" * 60)
        print("📬 INSTAGRAM INBOX SUMMARY")
        print("=" * 60)

        # Force stay on main handle for summary
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
                # Re-find thread element to avoid staleness
                current_btns = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="button"]')
                target_btn = None
                for btn in current_btns:
                    if name in btn.text:
                        target_btn = btn
                        break
                
                if target_btn:
                    self.driver.execute_script("arguments[0].click();", target_btn)
                    time.sleep(4)
                    
                    messages = self.get_messages(self.driver.current_url, limit=messages_per_thread)
                    if not messages:
                        print("     (No messages found yet or unable to parse DOM)")
                    else:
                        for msg in messages:
                            sender_icon = "🤖 You" if msg['role'] == 'assistant' else "👤 Them"
                            print(f"     {sender_icon}: {msg['content']}")
                
                # Head back to inbox safely
                self.driver.get('https://www.instagram.com/direct/inbox/')
                time.sleep(3)
            except Exception as e:
                print(f"     (Error reading messages: {e})")

        print(f"\n{'=' * 60}")
        print(f"  Total threads displayed: {len(threads)}")
        print("=" * 60 + "\n")
