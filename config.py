import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _parse_facebook_locations(
    raw_value: str,
) -> tuple[tuple[str, str], ...]:
    locations: list[tuple[str, str]] = []

    for entry in raw_value.split(","):
        entry = entry.strip()

        if not entry:
            continue

        if ":" in entry:
            slug, display_name = entry.split(
                ":",
                maxsplit=1,
            )
        else:
            slug = entry
            display_name = entry.replace(
                "-",
                " ",
            ).title()

        slug = slug.strip()
        display_name = display_name.strip()

        if slug and display_name:
            locations.append(
                (
                    slug,
                    display_name,
                )
            )

    return tuple(locations)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    default_country: str
    default_currency: str

    facebook_enabled: bool
    facebook_headless: bool
    facebook_enrich_details: bool
    facebook_detail_timeout_seconds: int
    facebook_max_results_per_location: int
    facebook_locations: tuple[
        tuple[str, str],
        ...
    ]

    carousell_results_limit: int

    ai_enabled: bool
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_timeout_seconds: float
    ai_max_listings_per_search: int
    ai_concurrency: int


settings = Settings(
    telegram_bot_token=os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    ).strip(),
    default_country=os.getenv(
        "DEFAULT_COUNTRY",
        "Malaysia",
    ).strip(),
    default_currency=os.getenv(
        "DEFAULT_CURRENCY",
        "MYR",
    ).strip(),

    facebook_enabled=_env_bool(
        "FACEBOOK_ENABLED",
        True,
    ),
    facebook_headless=_env_bool(
        "FACEBOOK_HEADLESS",
        False,
    ),
    facebook_enrich_details=_env_bool(
        "FACEBOOK_ENRICH_DETAILS",
        True,
    ),
    facebook_detail_timeout_seconds=_env_int(
        "FACEBOOK_DETAIL_TIMEOUT_SECONDS",
        15,
    ),
    facebook_max_results_per_location=_env_int(
        "FACEBOOK_MAX_RESULTS_PER_LOCATION",
        15,
    ),
    facebook_locations=_parse_facebook_locations(
        os.getenv(
            "FACEBOOK_LOCATIONS",
            (
                "kotakinabalu:Kota Kinabalu,"
                "kualalumpur:Kuala Lumpur"
            ),
        )
    ),

    carousell_results_limit=_env_int(
        "CAROUSELL_RESULTS_LIMIT",
        15,
    ),

    ai_enabled=_env_bool(
        "AI_ENABLED",
        False,
    ),
    ai_api_key=(
        os.getenv("PIKKAPI_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    ),
    ai_base_url=os.getenv(
        "PIKKAPI_BASE_URL",
        "https://pikkapi.cooltechgp.online/v1",
    ).strip().rstrip("/"),
    ai_model=os.getenv(
        "PIKKAPI_MODEL",
        "deepseek-v4-flash",
    ).strip(),
    ai_timeout_seconds=float(
        os.getenv("PIKKAPI_TIMEOUT_SECONDS", "45")
    ),
    ai_max_listings_per_search=_env_int(
        "AI_MAX_LISTINGS_PER_SEARCH",
        5,
    ),
    ai_concurrency=_env_int(
        "AI_CONCURRENCY",
        2,
    ),
)
