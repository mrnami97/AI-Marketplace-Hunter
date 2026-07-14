import logging
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext, Page, async_playwright

from crawler.base import Listing


logger = logging.getLogger(__name__)

BASE_URL = "https://www.carousell.com.my"
PROJECT_FOLDER = Path(__file__).resolve().parents[1]
PROFILE_FOLDER = PROJECT_FOLDER / "playwright-profile"
DEBUG_FOLDER = PROJECT_FOLDER / "debug-output"


def extract_price(text: str) -> float | None:
    match = re.search(
        r"\bRM\s*([\d,]+(?:\.\d{1,2})?)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def extract_posted_time(text: str) -> str | None:
    patterns = [
        r"\bjust now\b",
        r"\b\d+\s+(?:minute|minutes)\s+ago\b",
        r"\b\d+\s+(?:hour|hours)\s+ago\b",
        r"\b\d+\s+(?:day|days)\s+ago\b",
        r"\b\d+\s+(?:week|weeks)\s+ago\b",
        r"\b\d+\s+(?:month|months)\s+ago\b",
        r"\btoday\b",
        r"\byesterday\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)

    return None


def clean_text_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def choose_title(link_text: str, card_text: str) -> str:
    ignored = {
        "buyer protection",
        "like new",
        "lightly used",
        "well used",
        "brand new",
        "new",
    }

    for line in clean_text_lines(link_text) + clean_text_lines(card_text):
        if extract_price(line) is not None:
            continue
        if extract_posted_time(line) is not None:
            continue
        if line.lower() in ignored:
            continue
        if len(line) >= 6:
            return line[:150]

    return "Unknown Carousell listing"


async def close_popups(page: Page) -> None:
    selectors = [
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        'button:has-text("Skip")',
        'button:has-text("Got it")',
        'button:has-text("Not now")',
    ]

    for selector in selectors:
        try:
            button = page.locator(selector).first
            if await button.is_visible(timeout=500):
                await button.click(timeout=1_000)
                await page.wait_for_timeout(300)
        except Exception:
            pass


async def get_card_text(link) -> str:
    current = link
    best_text = ""

    for _ in range(8):
        try:
            text = (await current.inner_text()).strip()

            if text and len(text) > len(best_text):
                best_text = text

            if (
                extract_price(text) is not None
                and extract_posted_time(text) is not None
            ):
                return text

            parent = current.locator("xpath=..")
            if await parent.count() == 0:
                break

            current = parent

        except Exception:
            break

    return best_text


async def save_debug_files(page: Page) -> None:
    try:
        DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

        await page.screenshot(
            path=str(DEBUG_FOLDER / "carousell-search.png"),
            full_page=True,
        )

        (DEBUG_FOLDER / "carousell-search.html").write_text(
            await page.content(),
            encoding="utf-8",
        )
    except Exception as error:
        logger.warning("Could not save debug files: %s", error)


async def create_page(context: BrowserContext) -> Page:
    if context.pages:
        return context.pages[0]
    return await context.new_page()


async def search_carousell(
    query: str,
    max_price: float | None = None,
    max_results: int = 8,
) -> list[Listing]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

    search_url = f"{BASE_URL}/search/{quote_plus(cleaned_query)}"

    results: list[Listing] = []
    seen_urls: set[str] = set()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_FOLDER),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        try:
            page = await create_page(context)

            response = await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            logger.info(
                "Carousell opened: %s | status=%s",
                page.url,
                response.status if response else "none",
            )

            await page.wait_for_timeout(6_000)
            await close_popups(page)

            await page.mouse.wheel(0, 1_500)
            await page.wait_for_timeout(2_000)

            await save_debug_files(page)

            listing_links = page.locator('a[href*="/p/"]')
            listing_link_count = await listing_links.count()

            logger.info(
                "Possible Carousell listing links: %s",
                listing_link_count,
            )

            for index in range(listing_link_count):
                if len(results) >= max_results:
                    break

                link = listing_links.nth(index)

                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue

                    full_url = urljoin(BASE_URL, href)
                    clean_url = full_url.split("?")[0]

                    if clean_url in seen_urls:
                        continue

                    seen_urls.add(clean_url)

                    try:
                        link_text = (await link.inner_text()).strip()
                    except Exception:
                        link_text = ""

                    card_text = await get_card_text(link)
                    combined_text = f"{link_text}\n{card_text}".strip()

                    price = extract_price(combined_text)
                    posted_time = extract_posted_time(combined_text)

                    if max_price is not None:
                        if price is None or price > max_price:
                            continue

                    title = choose_title(link_text, card_text)

                    listing_id_match = re.search(
                        r"-(\d+)(?:/)?$",
                        clean_url,
                    )

                    listing_id = (
                        listing_id_match.group(1)
                        if listing_id_match
                        else clean_url.rstrip("/").split("/")[-1]
                    )

                    results.append(
                        Listing(
                            source="Carousell",
                            title=title,
                            price=price,
                            location=None,
                            posted_text=posted_time,
                            posted_at=None,
                            url=clean_url,
                            listing_id=listing_id,
                        )
                    )

                except Exception as error:
                    logger.warning(
                        "Skipped Carousell listing %s: %s",
                        index,
                        error,
                    )

            return results

        finally:
            await context.close()
