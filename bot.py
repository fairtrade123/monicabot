import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
ALLOWED_USERNAME = os.getenv("ALLOWED_USERNAME")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
MONICA_CHAT_ID = os.getenv("MONICA_CHAT_ID")

GROK_API_URL = "https://api.x.ai/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "bot.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

conversation_history = {}


def call_grok(chat_id, user_message):
    history = conversation_history.get(chat_id, [])
    history.append({"role": "user", "content": user_message})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    response = requests.post(
        GROK_API_URL,
        headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "grok-4",  
            "messages": messages,
            "temperature": 0.8,
        },
    )
    response.raise_for_status()
    reply = response.json()["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": reply})
    conversation_history[chat_id] = history
    return reply


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message is None or message.text is None:
        logger.warning(f"Received update with no usable text, ignoring: {update}")
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    message_text = message.text

    is_allowed_username = user.username == ALLOWED_USERNAME
    is_allowed_user_id = ALLOWED_USER_ID and str(user.id) == str(ALLOWED_USER_ID)

    if not (is_allowed_username or is_allowed_user_id):
        logger.info(f"Ignoring message from non-allowlisted user: {user.username} (id={user.id})")
        return

    logger.info(f"Message from {user.username}: {message_text}")

    try:
        reply = call_grok(chat_id, message_text)
    except Exception as e:
        logger.error(f"Grok API error: {e}")
        return

    if "[ESCALATE]" in reply:
        logger.info(f"Escalating chat with {user.username}")
        escalation_note = (
            f"\u26a0\ufe0f Escalation needed\n"
            f"User: @{user.username}\n"
            f"Message: {message_text}"
        )
        await context.bot.send_message(chat_id=MONICA_CHAT_ID, text=escalation_note)
        return  

    await update.message.reply_text(reply)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Unhandled exception: {context.error}", exc_info=context.error)


def main():
    logger.info("=== Bot starting up ===")
    try:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)
        logger.info("Bot initialized, starting polling...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Bot crashed on startup or during polling: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()