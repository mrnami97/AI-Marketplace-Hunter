import logging
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from crawler.base import Listing
from marketplace_utils import (
    is_blocked_listing,
    posted_age_minutes,
    relevance_score,
)


logger = logging.getLogger(__name__)

BASE_URL = "https://www.carousell.com.my"
PROJECT_FOLDER = Path(__file__).resolve().parents[1]
DEBUG_FOLDER = PROJECT_FOLDER / "debug-output"

MAX_LISTING_AGE_DAYS = 30
MAX_SCROLL_ROUNDS = 8


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
        r"\b\d+\s+(?:year|years)\s+ago\b",
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
        "promoted",
        "sponsored",
    }

    for line in clean_text_lines(link_text) + clean_text_lines(card_text):
        if extract_price(line) is not None:
            continue
        if extract_posted_time(line) is not None:
            continue
        if line.lower() in ignored:
            continue
        if len(line) >= 5:
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


async def get_listing_card(link: Locator) -> Locator:
    current = link
    best = link

    for _ in range(12):
        try:
            parent = current.locator("xpath=..")

            if await parent.count() == 0:
                break

            text = (await parent.inner_text()).strip()
            product_links = parent.locator('a[href*="/p/"]')
            product_link_count = await product_links.count()

            if (
                product_link_count == 1
                and extract_price(text) is not None
                and len(text) >= 12
            ):
                best = parent

                if extract_posted_time(text) is not None:
                    return parent

            if product_link_count > 1:
                break

            current = parent

        except Exception:
            break

    return best


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


async def launch_browser(playwright) -> Browser:
    try:
        return await playwright.chromium.launch(
            channel="chrome",
            headless=False,
        )
    except Exception:
        return await playwright.chromium.launch(
            headless=False,
        )


async def create_context(browser: Browser) -> BrowserContext:
    return await browser.new_context(
        viewport={"width": 1400, "height": 900},
        locale="en-MY",
        timezone_id="Asia/Kuala_Lumpur",
        service_workers="block",
    )


async def open_search_page(
    context: BrowserContext,
    search_url: str,
) -> Page:
    page = await context.new_page()

    try:
        await page.goto(
            search_url,
            wait_until="commit",
            timeout=30_000,
        )
    except PlaywrightTimeoutError:
        logger.warning("Navigation timed out: %s", page.url)

    if page.url == "about:blank":
        try:
            await page.goto(
                BASE_URL,
                wait_until="commit",
                timeout=30_000,
            )
            await page.wait_for_timeout(2_000)
            await page.goto(
                search_url,
                wait_until="commit",
                timeout=30_000,
            )
        except PlaywrightTimeoutError:
            logger.warning("Navigation retry timed out: %s", page.url)

    await page.wait_for_timeout(8_000)

    if page.url == "about:blank":
        raise RuntimeError("Chrome remained on about:blank.")

    return page


async def load_more_results(page: Page) -> int:
    previous_count = 0
    stable_rounds = 0

    for round_number in range(MAX_SCROLL_ROUNDS):
        links = page.locator('a[href*="/p/"]')
        current_count = await links.count()

        logger.info(
            "Scroll round %s: %s listing links",
            round_number + 1,
            current_count,
        )

        if current_count <= previous_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 2:
            break

        previous_count = current_count

        await page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        await page.wait_for_timeout(2_500)

        # Some infinite-scroll pages need a slight upward movement.
        await page.mouse.wheel(0, -300)
        await page.wait_for_timeout(500)
        await page.mouse.wheel(0, 1200)
        await page.wait_for_timeout(1_000)

    return await page.locator('a[href*="/p/"]').count()


async def search_carousell(
    query: str,
    max_price: float | None = None,
    max_results: int = 30,
) -> list[Listing]:
    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

    search_url = (
    f"{BASE_URL}/search/"
    f"{quote_plus(cleaned_query)}"
    "?addRecent=true"
    "&canChangeKeyword=true"
    "&includeSuggestions=true"
    "&sort_by=3"
    "&t-search_query_source=recent_search"
    )

    results = []
    seen_urls = set()

    async with async_playwright() as playwright:
        browser = await launch_browser(playwright)
        context = await create_context(browser)

        try:
            page = await open_search_page(context, search_url)
            await close_popups(page)

            try:
                await page.locator('a[href*="/p/"]').first.wait_for(
                    state="attached",
                    timeout=25_000,
                )
            except PlaywrightTimeoutError:
                logger.warning("No listing links appeared.")

            listing_link_count = await load_more_results(page)
            await save_debug_files(page)

            logger.info(
                "Total listing links after scrolling: %s",
                listing_link_count,
            )

            listing_links = page.locator('a[href*="/p/"]')
            read_limit = min(listing_link_count, max_results * 12)

            for index in range(read_limit):
                link = listing_links.nth(index)

                try:
                    href = await link.get_attribute("href")

                    if not href:
                        continue

                    clean_url = urljoin(BASE_URL, href).split("?")[0]

                    if clean_url in seen_urls:
                        continue

                    seen_urls.add(clean_url)

                    try:
                        link_text = (await link.inner_text()).strip()
                    except Exception:
                        link_text = ""

                    card = await get_listing_card(link)
                    card_text = (await card.inner_text()).strip()
                    combined_text = f"{link_text}\n{card_text}".strip()

                    price = extract_price(combined_text)
                    posted_time = extract_posted_time(card_text)
                    title = choose_title(link_text, card_text)

                    if is_blocked_listing(title, cleaned_query):
                        continue

                    # Wider threshold to keep abbreviations such as RTX2070S.
                    if relevance_score(title, cleaned_query) < 60:
                        continue

                    age_minutes = posted_age_minutes(posted_time)

                    if age_minutes > MAX_LISTING_AGE_DAYS * 24 * 60:
                        continue

                    if max_price is not None:
                        if price is None or price > max_price:
                            continue

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

                    if len(results) >= max_results:
                        break

                except Exception as error:
                    logger.warning(
                        "Skipped listing %s: %s",
                        index,
                        error,
                    )

            logger.info(
                "Returned %s filtered Carousell listings.",
                len(results),
            )

            return results

        finally:
            await context.close()
            await browser.close()
