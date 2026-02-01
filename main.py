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
    ig_engine = InstagramEngine(username) # Password still needed for fallback
    ig_engine.password = password
    bot = Chatbot(api_key, model=ai_model, base_url=base_url)

    # Login to Instagram
    try:
        ig_engine.login(session_id=session_id)
    except Exception as e:
        logger.error(f"Failed to login to Instagram: {e}")
        return

    logger.info("Bot is running and listening for messages...")

    while True:
        try:
            recent_threads = ig_engine.get_recent_threads(amount=10)
            
            for thread in recent_threads:
                # Get the last message in the thread
                if not thread.messages:
                    continue
                
                last_msg = thread.messages[0]
                
                # Logic: If the last message in the thread is NOT from the bot, it needs a reply
                if str(last_msg.user_id) == str(ig_engine.client.user_id):
                    # We are the last sender, no need to reply
                    continue
                
                user_text = last_msg.text
                thread_id = thread.id
                
                logger.info(f"Thread {thread_id} needs a reply. Last message: '{user_text}' from user {last_msg.user_id}")

                # Fetch conversation history
                try:
                    history_messages = ig_engine.client.direct_messages(thread_id, amount=context_limit)
                    # instagrapi returns newest first, we need oldest first for the LLM
                    history_messages.reverse()
                    
                    formatted_history = []
                    for h_msg in history_messages:
                        role = "assistant" if str(h_msg.user_id) == str(ig_engine.client.user_id) else "user"
                        if h_msg.text: # Only include text messages
                            formatted_history.append({"role": role, "content": h_msg.text})
                    
                    # Generate AI response with history
                    ai_response = bot.generate_response(formatted_history)
                except Exception as e:
                    logger.error(f"Error fetching history for thread {thread_id}: {e}")
                    # Fallback to single message if history fails
                    ai_response = bot.generate_response([{"role": "user", "content": user_text}])
                
                # Send response
                if ig_engine.send_message(thread_id, ai_response):
                    logger.info(f"Successfully replied to thread {thread_id}")
                    # Note: Depending on instagrapi version, we might need to marks as read
                    # but usually sending a message handles the thread state.
                
            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            logger.info("Bot stopping...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(10) # Wait a bit before retrying after an error

if __name__ == "__main__":
    main()
