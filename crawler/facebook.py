import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from collections.abc import Awaitable, Callable

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from config import settings
from crawler.base import Listing
from marketplace_utils import (
    is_blocked_listing,
    model_matches_query,
    relevance_score,
)


logger = logging.getLogger(__name__)

BASE_URL = "https://www.facebook.com"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = PROJECT_ROOT / "facebook-profile"
DEBUG_DIR = PROJECT_ROOT / "debug-output"

MAX_SCROLL_ROUNDS = 15
STABLE_ROUNDS_TO_STOP = 4
MIN_RELEVANCE = 80

ProgressCallback = Callable[[int, str], Awaitable[None]]

POSTED_PATTERNS = [
    r"\bjust listed\b",
    r"\blisted \d+\s+(?:minute|minutes)\s+ago\b",
    r"\blisted \d+\s+(?:hour|hours)\s+ago\b",
    r"\blisted \d+\s+(?:day|days)\s+ago\b",
    r"\b\d+\s+(?:minute|minutes)\s+ago\b",
    r"\b\d+\s+(?:hour|hours)\s+ago\b",
    r"\b\d+\s+(?:day|days)\s+ago\b",
    r"\b\d+\s+(?:week|weeks)\s+ago\b",
]


@dataclass(frozen=True)
class RawFacebookCard:
    url: str
    text: str


def extract_price(text: str) -> float | None:
    patterns = [
        r"\bRM\s*([\d,]+(?:\.\d{1,2})?)",
        r"\bMYR\s*([\d,]+(?:\.\d{1,2})?)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        try:
            return float(
                match.group(1).replace(",", "")
            )
        except ValueError:
            continue

    return None


def extract_posted_text(text: str) -> str | None:
    for pattern in POSTED_PATTERNS:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(0)

    return None


def clean_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def is_price_line(line: str) -> bool:
    normalized = line.strip()

    return bool(
        re.fullmatch(
            r"(?:RM|MYR)\s*[\d,]+(?:\.\d{1,2})?",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def is_posted_line(line: str) -> bool:
    return extract_posted_text(line) is not None


def choose_title(
    card_text: str,
    query: str,
) -> str | None:
    """
    Facebook item anchors already contain:
    price -> optional old price -> title -> location.

    Select the line matching the requested model family.
    """
    candidates: list[str] = []

    for line in clean_lines(card_text):
        if is_price_line(line):
            continue

        if is_posted_line(line):
            continue

        if len(line) < 4:
            continue

        if model_matches_query(
            line,
            query,
        ):
            candidates.append(line)

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda line: (
            relevance_score(
                line,
                query,
            ),
            -abs(len(line) - 45),
        ),
        reverse=True,
    )

    return ranked[0][:150]


def extract_location(
    card_text: str,
    fallback_location: str,
) -> str:
    lines = clean_lines(card_text)

    for line in reversed(lines):
        if is_price_line(line):
            continue

        if is_posted_line(line):
            continue

        if re.search(
            r",\s*(?:SBH|SWK|SGR|WLY|JHR|PNG|PRK|KDH|"
            r"MLK|NGS|PHG|TRG|KTN|PLS|LBN)\b",
            line,
            flags=re.IGNORECASE,
        ):
            return line[:100]

    return fallback_location


def extract_listing_id(url: str) -> str:
    match = re.search(
        r"/marketplace/item/(\d+)",
        url,
    )

    if match:
        return match.group(1)

    return url.rstrip("/").split("/")[-1]


async def save_debug(
    page: Page,
    location_slug: str,
) -> None:
    DEBUG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        await page.screenshot(
            path=str(
                DEBUG_DIR
                / f"facebook-marketplace-{location_slug}.png"
            ),
            full_page=True,
        )

        (
            DEBUG_DIR
            / f"facebook-marketplace-{location_slug}.html"
        ).write_text(
            await page.content(),
            encoding="utf-8",
        )

    except Exception as error:
        logger.warning(
            "Could not save Facebook debug files: %s",
            error,
        )


async def capture_visible_cards(
    page: Page,
) -> list[RawFacebookCard]:
    """
    Capture all currently rendered Marketplace cards.

    Facebook virtualizes the grid, so cards that were visible earlier can
    disappear from the DOM after scrolling. We therefore collect cards on
    every scroll round instead of inspecting the DOM only at the end.
    """
    raw_items = await page.locator(
        'a[href*="/marketplace/item/"]'
    ).evaluate_all(
        """
        (anchors) => anchors.map((anchor) => ({
            href: anchor.getAttribute("href") || "",
            text: (anchor.innerText || anchor.textContent || "").trim()
        }))
        """
    )

    cards: list[RawFacebookCard] = []

    for item in raw_items:
        href = str(item.get("href", "")).strip()
        text = str(item.get("text", "")).strip()

        if not href or not text:
            continue

        clean_url = urljoin(
            BASE_URL,
            href,
        ).split("?")[0]

        cards.append(
            RawFacebookCard(
                url=clean_url,
                text=text,
            )
        )

    return cards


async def collect_cards_during_scroll(
    page: Page,
    location_name: str,
    progress_callback: ProgressCallback | None = None,
    progress_start: int = 40,
    progress_end: int = 90,
) -> list[RawFacebookCard]:
    collected: dict[str, RawFacebookCard] = {}
    stable_rounds = 0
    previous_total = 0

    for round_number in range(
        MAX_SCROLL_ROUNDS
    ):
        visible_cards = await capture_visible_cards(
            page
        )

        for card in visible_cards:
            existing = collected.get(card.url)

            # Prefer the version containing more visible text.
            if (
                existing is None
                or len(card.text) > len(existing.text)
            ):
                collected[card.url] = card

        current_total = len(collected)

        logger.info(
            "Facebook %s round %s: "
            "%s visible anchors, %s unique cards collected",
            location_name,
            round_number + 1,
            len(visible_cards),
            current_total,
        )

        if progress_callback is not None:
            round_fraction = (
                (round_number + 1)
                / MAX_SCROLL_ROUNDS
            )

            progress_value = round(
                progress_start
                + (
                    progress_end
                    - progress_start
                )
                * round_fraction
            )

            await progress_callback(
                min(progress_value, progress_end),
                (
                    f"Facebook {location_name}: "
                    f"scroll {round_number + 1}/"
                    f"{MAX_SCROLL_ROUNDS}, "
                    f"{current_total} cards collected"
                ),
            )

        if current_total <= previous_total:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= STABLE_ROUNDS_TO_STOP:
            break

        previous_total = current_total

        await page.evaluate(
            "window.scrollBy(0, Math.max(window.innerHeight * 1.6, 1200))"
        )

        await page.wait_for_timeout(
            1_800
        )

    # One final capture after the last movement.
    for card in await capture_visible_cards(page):
        existing = collected.get(card.url)

        if (
            existing is None
            or len(card.text) > len(existing.text)
        ):
            collected[card.url] = card

    return list(collected.values())


def select_locations(
    requested_location: str | None,
) -> tuple[tuple[str, str], ...]:
    configured = settings.facebook_locations

    if not requested_location:
        return configured

    requested = requested_location.lower().strip()

    selected = tuple(
        item
        for item in configured
        if (
            requested in item[1].lower()
            or item[1].lower() in requested
            or requested == item[0].lower()
        )
    )

    return selected or configured


async def search_facebook_marketplace(
    query: str,
    max_price: float | None = None,
    max_results: int = 30,
    location: str | None = None,
    progress_callback: ProgressCallback | None = None,
    progress_start: int = 40,
    progress_end: int = 90,
) -> list[Listing]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    if not settings.facebook_enabled:
        return []

    if not PROFILE_DIR.exists():
        raise RuntimeError(
            "Facebook profile not found. "
            "Run: py facebook_login.py"
        )

    selected_locations = select_locations(
        location
    )

    results: list[Listing] = []

    async with async_playwright() as playwright:
        context: BrowserContext = (
            await playwright.chromium
            .launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=settings.facebook_headless,
                viewport={
                    "width": 1400,
                    "height": 900,
                },
                locale="en-MY",
                timezone_id="Asia/Kuala_Lumpur",
            )
        )

        try:
            page = (
                context.pages[0]
                if context.pages
                else await context.new_page()
            )

            location_count = max(
                len(selected_locations),
                1,
            )

            for location_index, (
                location_slug,
                location_name,
            ) in enumerate(selected_locations):
                location_start = round(
                    progress_start
                    + (
                        progress_end
                        - progress_start
                    )
                    * location_index
                    / location_count
                )

                location_end = round(
                    progress_start
                    + (
                        progress_end
                        - progress_start
                    )
                    * (location_index + 1)
                    / location_count
                )

                if progress_callback is not None:
                    await progress_callback(
                        location_start,
                        (
                            f"Opening Facebook "
                            f"{location_name}"
                        ),
                    )
                search_url = (
                    f"{BASE_URL}/marketplace/"
                    f"{location_slug}/search"
                    f"?query={quote_plus(cleaned_query)}"
                )

                logger.info(
                    "Opening Facebook Marketplace %s: %s",
                    location_name,
                    search_url,
                )

                try:
                    await page.goto(
                        search_url,
                        wait_until="commit",
                        timeout=60_000,
                    )

                except PlaywrightTimeoutError:
                    logger.warning(
                        "Facebook navigation timed out. URL: %s",
                        page.url,
                    )

                await page.wait_for_timeout(
                    7_000
                )

                if "/login" in page.url:
                    raise RuntimeError(
                        "Facebook login session expired. "
                        "Run: py facebook_login.py"
                    )

                try:
                    await page.locator(
                        'a[href*="/marketplace/item/"]'
                    ).first.wait_for(
                        state="attached",
                        timeout=25_000,
                    )

                except PlaywrightTimeoutError:
                    logger.warning(
                        "No Facebook item links appeared for %s.",
                        location_name,
                    )

                raw_cards = await collect_cards_during_scroll(
                    page=page,
                    location_name=location_name,
                    progress_callback=progress_callback,
                    progress_start=location_start,
                    progress_end=max(
                        location_start,
                        location_end - 3,
                    ),
                )

                await save_debug(
                    page,
                    location_slug,
                )

                accepted: list[Listing] = []
                seen_content: set[
                    tuple[str, int | None]
                ] = set()

                for card in raw_cards:
                    title = choose_title(
                        card.text,
                        cleaned_query,
                    )

                    if not title:
                        continue

                    if is_blocked_listing(
                        title,
                        cleaned_query,
                    ):
                        continue

                    if relevance_score(
                        title,
                        cleaned_query,
                    ) < MIN_RELEVANCE:
                        continue

                    price = extract_price(
                        card.text
                    )

                    if max_price is not None:
                        if (
                            price is None
                            or price > max_price
                        ):
                            continue

                    content_key = (
                        re.sub(
                            r"[^a-z0-9]",
                            "",
                            title.lower(),
                        ),
                        (
                            int(round(price))
                            if price is not None
                            else None
                        ),
                    )

                    if content_key in seen_content:
                        continue

                    seen_content.add(content_key)

                    accepted.append(
                        Listing(
                            source="Facebook Marketplace",
                            title=title,
                            price=price,
                            location=extract_location(
                                card.text,
                                location_name,
                            ),
                            posted_text=extract_posted_text(
                                card.text
                            ),
                            posted_at=None,
                            url=card.url,
                            listing_id=extract_listing_id(
                                card.url
                            ),
                        )
                    )

                accepted.sort(
                    key=lambda listing: (
                        listing.price is None,
                        (
                            listing.price
                            if listing.price is not None
                            else float("inf")
                        ),
                    )
                )

                location_limit = min(
                    settings.facebook_max_results_per_location,
                    max_results,
                )

                accepted = accepted[
                    :location_limit
                ]

                logger.info(
                    "Facebook %s: %s raw unique cards, "
                    "%s matching listings accepted.",
                    location_name,
                    len(raw_cards),
                    len(accepted),
                )

                results.extend(
                    accepted
                )

                if progress_callback is not None:
                    await progress_callback(
                        location_end,
                        (
                            f"Facebook {location_name}: "
                            f"{len(accepted)} matches"
                        ),
                    )

            return results

        finally:
            await context.close()
