import logging

from telegram.ext import Application, CommandHandler

from config import settings
from database import init_db
from handlers import (
    current_listings,
    help_command,
    list_watches,
    manual_check,
    remove_watch,
    search,
    start,
    status_command,
    watch,
)
from watcher import check_all_watches


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue unavailable. Run: "
            "py -m pip install 'python-telegram-bot[job-queue]'"
        )

    application.job_queue.run_repeating(
        callback=check_all_watches,
        interval=300,
        first=15,
        name="marketplace-watch-checker",
    )

    print("Automatic watcher scheduled every 5 minutes.")


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing from .env"
        )

    init_db()

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("watch", watch))
    application.add_handler(CommandHandler("list", list_watches))
    application.add_handler(CommandHandler("remove", remove_watch))
    application.add_handler(CommandHandler("current", current_listings))
    application.add_handler(CommandHandler("check", manual_check))
    application.add_handler(CommandHandler("status", status_command))

    print("AI Marketplace Hunter v0.2.2 is running...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
