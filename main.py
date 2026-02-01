import os
import time
import logging
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
    session_id = os.getenv("INSTAGRAM_SESSION_ID") # Optional
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    ai_model = os.getenv("AI_MODEL")
    check_interval = int(os.getenv("CHECK_INTERVAL", 60))
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
        logger.error(f"Missing required environment variables for {llm_provider} or Instagram. Please check your .env file.")
        return

    # Initialize components
    ig_engine = InstagramEngine(username, password)
    bot = Chatbot(api_key, model=ai_model, base_url=base_url)

    # Login and Start Engine
    try:
        ig_engine.start(headless=False) # Run in visible mode
        ig_engine.login(session_id=session_id)
    except Exception as e:
        logger.error(f"Failed to initialize Playwright engine: {e}")
        return

    logger.info("Bot is running (Playwright Mode)...")

    while True:
        try:
            recent_threads = ig_engine.get_recent_threads(amount=10)
            
            for thread_info in recent_threads:
                thread_id = thread_info['id']
                
                # Fetch messages for this thread
                history = ig_engine.get_messages(thread_id, amount=context_limit)
                
                if not history:
                    continue
                
                # Check if the last message is from the user
                last_msg = history[-1]
                if last_msg['role'] == 'assistant':
                    # Already replied or we sent the last message
                    continue

                logger.info(f"Thread {thread_id} needs a reply. Last message: '{last_msg['content']}'")

                # Generate AI response
                ai_response = bot.generate_response(history)
                
                # Send response
                if ig_engine.send_message(thread_id, ai_response):
                    logger.info(f"Successfully replied to thread {thread_id}")
                
            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            logger.info("Bot stopping...")
            ig_engine.stop()
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
