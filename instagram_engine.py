import os
import time
import logging
import random
from playwright.sync_api import sync_playwright

class InstagramEngine:
    def __init__(self, username, password=None):
        self.username = username
        self.password = password
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.user_data_dir = "playwright_session"
        self.logger = logging.getLogger(__name__)

    def start(self, headless=False):
        """Initializes the browser. Set headless=False to see the actions."""
        self.playwright = sync_playwright().start()
        self.logger.info("Initializing Chromium browser...")
        
        # Using launch_persistent_context to save session/cookies
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=headless,
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.logger.info(f"Browser started (headless={headless})")

    def handle_popups(self):
        """Handles common Instagram popups that block navigation."""
        popups = ["Not Now", "Save Info", "Allow all cookies", "Allow"]
        for text in popups:
            try:
                # Use a short timeout to check if the button is there
                btn = self.page.get_by_role("button", name=text, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    self.logger.info(f"Found popup button '{text}', clicking...")
                    btn.first.click()
                    time.sleep(2)
            except Exception:
                pass

    def stop(self):
        """Closes the browser."""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def login(self, session_id=None):
        """Logins to Instagram via UI or Session ID."""
        if not self.page:
            self.start()

        # Try to set session ID cookie if provided
        if session_id:
            self.logger.info(f"Injecting SESSION_ID: {session_id[:10]}...")
            self.context.add_cookies([{
                'name': 'sessionid',
                'value': session_id,
                'domain': '.instagram.com',
                'path': '/'
            }])

        self.logger.info("Navigating to Instagram Home...")
        self.page.goto("https://www.instagram.com/")
        time.sleep(5)
        self.handle_popups()

        # Check if already logged in (look for search icon or profile)
        if self.page.query_selector('svg[aria-label="Direct"]') or "direct/inbox" in self.page.url:
            self.logger.info("Logged in successfully (session detected).")
            return True

        if "login" not in self.page.url and self.page.query_selector('input[name="username"]'):
            pass # We are on the login form
        elif "direct/inbox" not in self.page.url:
            self.logger.info("Redirected to login or home, checking state...")

        # Perform UI login if visible
        try:
            # Try specific selectors provided by user or standard ones
            username_field = self.page.query_selector('input[name="email"]') or self.page.query_selector('input[name="username"]')
            password_field = self.page.query_selector('input[name="pass"]') or self.page.query_selector('input[name="password"]')

            if username_field and password_field:
                if not self.password:
                    self.logger.error("Login form visible but no password provided in .env!")
                    return False
                
                self.logger.info("Performing UI login with provided credentials...")
                username_field.fill(self.username)
                password_field.fill(self.password)
                
                # Try to click the "Log in" button
                login_btn = self.page.get_by_text("Log in", exact=True)
                if login_btn.count() > 0:
                    login_btn.first.click()
                else:
                    # Fallback to submit button
                    self.page.click('button[type="submit"]')
                
                self.logger.info("Waiting for login to complete...")
                self.page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(5)
                self.handle_popups()
                return True
        except Exception as e:
            if self.page.query_selector('svg[aria-label="Direct"]'):
                return True
            self.logger.warning(f"Login process encountered an issue: {e}")
        
        return False

    def get_recent_threads(self, amount=10):
        """Scrapes the inbox for recent threads with logging."""
        try:
            self.logger.info("Fetching recent threads from inbox...")
            self.page.goto("https://www.instagram.com/direct/inbox/")
            time.sleep(3)
            self.handle_popups()

            # Wait for thread items
            self.page.wait_for_selector('a[href^="/direct/t/"]', timeout=15000)
            threads_elements = self.page.query_selector_all('a[href^="/direct/t/"]')
            
            self.logger.info(f"Found {len(threads_elements)} threads in side panel.")
            
            recent_threads = []
            for i, elem in enumerate(threads_elements[:amount]):
                href = elem.get_attribute('href')
                thread_id = href.split('/')[-2] if href.endswith('/') else href.split('/')[-1]
                
                recent_threads.append({
                    'id': thread_id,
                    'href': href
                })
            
            return recent_threads
        except Exception as e:
            self.logger.error(f"Error fetching threads: {e}")
            return []

    def get_messages(self, thread_id, amount=20):
        """Fetches messages from a specific thread with context extraction."""
        try:
            self.logger.info(f"Opening thread {thread_id}...")
            self.page.goto(f"https://www.instagram.com/direct/t/{thread_id}/")
            
            # Wait for the messages container
            # Instagram messages are in divs with role="row"
            self.page.wait_for_selector('div[role="row"]', timeout=10000)
            time.sleep(2) # Wait for animations
            
            rows = self.page.query_selector_all('div[role="row"]')
            self.logger.info(f"Extracted {len(rows)} message rows for thread {thread_id}")
            
            messages = []
            for row in rows[-amount:]:
                try:
                    # Look for the text inside the row
                    # Often messages are in a div with some padding
                    # We pick the span or div that has the actual text
                    text_nodes = row.query_selector_all('span')
                    if not text_nodes: continue
                    
                    # Usually the last span in the row contains the main text
                    text = text_nodes[-1].inner_text().strip()
                    if not text: continue

                    # Check alignment to determine role
                    # Instagram uses flexbox; 'flex-end' means it's our message
                    style = row.get_attribute('style') or ""
                    # Also check parent div alignment
                    parent_style = row.evaluate("el => window.get_computedStyle(el).justifyContent")
                    
                    is_mine = "flex-end" in style or "flex-end" in parent_style
                    
                    messages.append({
                        'role': 'assistant' if is_mine else 'user',
                        'content': text
                    })
                except:
                    continue
            
            self.logger.info(f"Finished processing {len(messages)} valid messages.")
            return messages
        except Exception as e:
            self.logger.error(f"Error fetching messages for {thread_id}: {e}")
            return []

    def send_message(self, thread_id, text):
        """Sends a message by typing into the visible textbox."""
        try:
            self.logger.info(f"Sending response to {thread_id}...")
            # Ensure we are on the right page
            if f"/direct/t/{thread_id}" not in self.page.url:
                self.page.goto(f"https://www.instagram.com/direct/t/{thread_id}/")
            
            # Find the input box
            textarea = self.page.wait_for_selector('div[role="textbox"]', timeout=10000)
            
            # Type and Send
            textarea.click()
            self.page.keyboard.type(text, delay=random.uniform(30, 70))
            time.sleep(1)
            self.page.keyboard.press("Enter")
            
            self.logger.info("Message sent successfully via browser emulation.")
            time.sleep(random.uniform(2, 4))
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
