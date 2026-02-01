import os
import logging
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

class InstagramEngine:
    def __init__(self, username, password=None):
        self.username = username
        self.password = password
        self.client = Client()
        self.settings_file = "instagram_settings.json"
        self.logger = logging.getLogger(__name__)

    def login(self, session_id=None):
        """Attempts to login using various methods."""
        # Add basic human-like delay configuration
        self.client.delay_range = [5, 10]
        
        # If session_id is provided, try logging in with it first
        if session_id:
            try:
                self.logger.info("Attempting login via SESSION_ID...")
                self.client.login_by_sessionid(session_id)
                self.logger.info("Logged in successfully using SESSION_ID.")
                return True
            except Exception as e:
                self.logger.error(f"SESSION_ID login failed: {e}")

        # Try loading previous session settings
        if os.path.exists(self.settings_file):
            try:
                self.client.load_settings(self.settings_file)
                self.client.login(self.username, self.password)
                self.logger.info("Logged in using existing settings.")
                return True
            except Exception as e:
                self.logger.warning(f"Could not login with settings: {e}")
        
        return self.login_new()

    def login_new(self):
        """Performs a fresh login with a new device seed."""
        try:
            self.logger.info("Logging in with fresh credentials...")
            self.client.login(self.username, self.password)
            self.client.dump_settings(self.settings_file)
            self.logger.info("Successfully logged in and saved settings.")
            return True
        except Exception as e:
            self.logger.error(f"Fresh login failed: {e}")
            raise e

    def get_recent_threads(self, amount=20):
        """Fetches recent message threads from the inbox."""
        try:
            threads = self.client.direct_threads(amount=amount)
            return threads
        except Exception as e:
            self.logger.error(f"Error fetching recent threads: {e}")
            return []

    def reset_session(self):
        """Deletes settings file and re-logs in."""
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        self.login_new()

    def send_message(self, thread_id, text, retry=1):
        """Sends a message to a specific thread with fallback, delay, and retry."""
        import time
        import random
        
        try:
            # Mimic human delay
            time.sleep(random.uniform(3, 7))
            
            # Try direct_send first
            try:
                self.client.direct_send(text, thread_ids=[thread_id])
                self.logger.info(f"Sent message via direct_send to thread {thread_id}")
                return True
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg or "not found" in error_msg.lower():
                    self.logger.warning(f"direct_send hit 404, trying direct_answer fallback")
                    self.client.direct_answer(thread_id, text)
                    self.logger.info(f"Sent message via direct_answer to thread {thread_id}")
                    return True
                
                if retry > 0:
                    self.logger.warning(f"Generic send error: {error_msg}. Retrying in 10s...")
                    time.sleep(10)
                    return self.send_message(thread_id, text, retry=retry-1)
                
                raise e
                
        except Exception as e:
            self.logger.error(f"Error sending message to {thread_id}: {e}")
            return False

    def mark_as_read(self, thread_id):
        """Marks a thread as read."""
        try:
            # Note: direct_answer might mark it as read, but explicitly doing it depends on usage
            # self.client.direct_thread_mark_unread(thread_id, False) # This is not always reliable
            pass
        except Exception as e:
            self.logger.error(f"Error marking thread as read: {e}")
