import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    default_country: str = os.getenv("DEFAULT_COUNTRY", "Malaysia").strip()
    default_currency: str = os.getenv("DEFAULT_CURRENCY", "MYR").strip()

settings = Settings()
