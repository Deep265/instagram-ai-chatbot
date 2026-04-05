import os
import time
import logging
import random
from dotenv import load_dotenv
from instagram_engine import InstagramEngine
from chatbot import Chatbot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    load_dotenv()

    # Load environment variables
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    session_id = os.getenv("INSTAGRAM_SESSION_ID")
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    ai_model = os.getenv("AI_MODEL")
    context_limit = int(os.getenv("CONTEXT_LIMIT", 20))

    # Determine which API key and model to use
    api_key = None
    base_url = None

    if llm_provider == "groq":
        api_key = groq_key
        base_url = "https://api.groq.com/openai/v1"
        if not ai_model:
            ai_model = "llama3-8b-8192"
    elif llm_provider == "openrouter":
        api_key = openrouter_key
        base_url = "https://openrouter.ai/api/v1"
        if not ai_model:
            ai_model = "upstage/solar-pro-3:free"
    else:
        api_key = openai_key
        if not ai_model:
            ai_model = "gpt-3.5-turbo"

    if not api_key or not username or not password:
        logger.error(f"Missing required environment variables for {llm_provider} or Instagram.")
        return

    # Initialize components
    ig_engine = InstagramEngine(logger, username, password)
    bot = Chatbot(api_key, model=ai_model, base_url=base_url)

    # Login and Start Engine
    try:
        ig_engine.start(headless=False)
        if not ig_engine.login(session_id=session_id):
            logger.error("Login failed. Shutting down bot.")
            ig_engine.stop()
            return
    except Exception as e:
        logger.error(f"Failed to initialize engine: {e}")
        ig_engine.stop()
        return

    logger.info("Login successful! Starting Parallel Tabbed Worker System...")
    
    # Initial Inbox Summary
    ig_engine.print_inbox_summary(max_threads=5, messages_per_thread=5)

    # ============================================================
    # MULTITASKING LOOP
    # ============================================================
    logger.info("Parallel Tabbed Worker System Active. Heartbeat active.")
    
    last_inbox_check = 0
    inbox_check_interval = 60 # Check for new people once every minute

    while True:
        try:
            # 1. Check Driver Health
            try:
                _ = ig_engine.driver.current_window_handle
            except Exception:
                logger.error("Browser session lost. Attempting to restart...")
                ig_engine.stop()
                time.sleep(5)
                ig_engine.start(headless=False)
                ig_engine.login(session_id=session_id)
                continue

            # 2. Poll Inbox for NEW Unread Threads (Only every 60 seconds)
            if time.time() - last_inbox_check > inbox_check_interval:
                logger.info("Scanning inbox for NEW conversations...")
                recent_threads = ig_engine.get_recent_threads(amount=10)
                unread_threads = [t for t in recent_threads if t.get('is_unread', False)]
                
                if unread_threads:
                    logger.info(f"Found {len(unread_threads)} people requiring attention.")
                    # 3. Open tabs for any NEW people
                    for thread in unread_threads:
                        name = thread['name']
                        if name not in ig_engine.tabs:
                            if len(ig_engine.tabs) < 5:
                                if ig_engine.ensure_thread_tab(name, thread['element']):
                                    # Return to main handle to finish scanning others
                                    ig_engine.driver.switch_to.window(ig_engine.main_handle)
                            else:
                                logger.warning(f"Slot full! Cannot open tab for {name} yet.")
                
                last_inbox_check = time.time()

            # 4. Process All Active Worker Tabs (No Refresh)
            active_names = list(ig_engine.tabs.keys())
            for name in active_names:
                try:
                    handle = ig_engine.tabs[name]
                    if handle in ig_engine.driver.window_handles:
                        ig_engine.driver.switch_to.window(handle)
                        time.sleep(1) # Wait for DOM
                        
                        # Read messages (reads from current tab DOM)
                        current_url = ig_engine.driver.current_url
                        history = ig_engine.get_messages(current_url, limit=context_limit)
                        
                        if not history:
                            continue
                            
                        last_msg = history[-1]
                        if last_msg['role'] == 'user':
                            logger.info(f"Nyra is thinking for {name}...")
                            ai_response = bot.generate_response(history)
                            
                            # Check for [SILENCE] tag
                            if ai_response.startswith("[SILENCE]"):
                                logger.info(f"[AI Decision] Staying silent for {name}: {ai_response}")
                                continue

                            if ig_engine.send_message(current_url, ai_response):
                                logger.info(f"Replied to {name}. Staying on tab for follow-ups.")
                                time.sleep(2)
                except Exception as e:
                    logger.error(f"Worker tab error ({name}): {e}")
                    # Only close if the window was actually shut by the user
                    if handle not in ig_engine.driver.window_handles:
                        del ig_engine.tabs[name]

            # 5. Small pacing delay between whole-system cycles
            time.sleep(random.uniform(3.0, 6.0))
            
        except KeyboardInterrupt:
            logger.info("Bot stopping...")
            ig_engine.stop()
            break
        except Exception as e:
            logger.error(f"Multitasking loop error: {e}")
            try:
                if ig_engine.main_handle:
                    ig_engine.driver.switch_to.window(ig_engine.main_handle)
            except: pass
            time.sleep(10)

if __name__ == "__main__":
    main()
