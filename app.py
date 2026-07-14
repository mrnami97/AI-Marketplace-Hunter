import logging
from telegram.ext import Application, CommandHandler
from config import settings
from database import init_db
from handlers import start, help_command, search, watch, list_watches, remove_watch

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")

    init_db()

    application = Application.builder().token(settings.telegram_bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("watch", watch))
    application.add_handler(CommandHandler("list", list_watches))
    application.add_handler(CommandHandler("remove", remove_watch))

    print("AI Marketplace Hunter is running...")
    application.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
