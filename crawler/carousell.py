import logging
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext, Page, async_playwright

from crawler.base import Listing


logger = logging.getLogger(__name__)

BASE_URL = "https://www.carousell.com.my"

# These folders will be created in the main project folder.
PROJECT_FOLDER = Path(__file__).resolve().parents[1]
PROFILE_FOLDER = PROJECT_FOLDER / "playwright-profile"
DEBUG_FOLDER = PROJECT_FOLDER / "debug-output"


def extract_price(text: str) -> float | None:
    """
    Extract a Malaysian Ringgit price from text.

    Examples:
        RM1,100 -> 1100.0
        RM 850  -> 850.0
    """
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
    """
    Extract visible Carousell posted-time text.
    """
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
    """
    Split card text into clean, non-empty lines.
    """
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def choose_title(link_text: str, card_text: str) -> str:
    """
    Choose the most likely listing title.
    """
    link_lines = clean_text_lines(link_text)

    for line in link_lines:
        if extract_price(line) is not None:
            continue

        if extract_posted_time(line) is not None:
            continue

        if line.lower() in {
            "buyer protection",
            "like new",
            "lightly used",
            "well used",
            "brand new",
            "new",
        }:
            continue

        if len(line) >= 6:
            return line[:150]

    card_lines = clean_text_lines(card_text)

    for line in card_lines:
        if extract_price(line) is not None:
            continue

        if extract_posted_time(line) is not None:
            continue

        if line.lower() in {
            "buyer protection",
            "like new",
            "lightly used",
            "well used",
            "brand new",
            "new",
        }:
            continue

        if len(line) >= 8:
            return line[:150]

    return "Unknown Carousell listing"


async def close_popups(page: Page) -> None:
    """
    Attempt to close common Carousell popups.

    Failure to find a popup is not treated as an error.
    """
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

    # Handle the "Buy safely on Carousell" popup.
    try:
        popup_title = page.get_by_text(
            "Buy safely on Carousell",
            exact=False,
        )

        if await popup_title.is_visible(timeout=1_000):
            dialog = popup_title.locator(
                "xpath=ancestor::*[@role='dialog'][1]"
            )

            if await dialog.count() > 0:
                close_buttons = dialog.locator(
                    'button[aria-label="Close"], '
                    'button[aria-label="close"], '
                    "button"
                )

                button_count = await close_buttons.count()

                for index in range(button_count):
                    button = close_buttons.nth(index)

                    try:
                        if await button.is_visible():
                            await button.click(timeout=1_000)
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        continue

    except Exception:
        pass


async def get_card_text(link) -> str:
    """
    Move upward from the listing link until a container containing
    listing information such as price or posted time is found.
    """
    current = link
    best_text = ""

    for _ in range(8):
        try:
            text = (await current.inner_text()).strip()

            if text and len(text) > len(best_text):
                best_text = text

            has_price = extract_price(text) is not None
            has_posted_time = extract_posted_time(text) is not None

            if has_price and has_posted_time:
                return text

            parent = current.locator("xpath=..")

            if await parent.count() == 0:
                break

            current = parent

        except Exception:
            break

    return best_text


async def save_debug_files(page: Page) -> None:
    """
    Save the current page screenshot and HTML for troubleshooting.
    """
    try:
        DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

        screenshot_path = DEBUG_FOLDER / "carousell-search.png"
        html_path = DEBUG_FOLDER / "carousell-search.html"

        await page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        html_path.write_text(
            await page.content(),
            encoding="utf-8",
        )

        print(f"Debug screenshot: {screenshot_path}")
        print(f"Debug HTML: {html_path}")

    except Exception as error:
        logger.warning("Could not save debug files: %s", error)


async def create_page(context: BrowserContext) -> Page:
    """
    Reuse the initial Playwright page when available.
    """
    if context.pages:
        return context.pages[0]

    return await context.new_page()


async def search_carousell(
    query: str,
    max_price: float | None = None,
    max_results: int = 8,
) -> list[Listing]:
    """
    Search Carousell and return normalized Listing objects.
    """
    print(">>> CAROUSELL CRAWLER STARTED <<<")

    cleaned_query = query.strip()

    if not cleaned_query:
        return []

    PROFILE_FOLDER.mkdir(parents=True, exist_ok=True)
    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

    search_url = (
        f"{BASE_URL}/search/"
        f"{quote_plus(cleaned_query)}"
    )

    results: list[Listing] = []
    seen_urls: set[str] = set()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_FOLDER),
            headless=False,
            viewport={
                "width": 1400,
                "height": 900,
            },
        )

        try:
            page = await create_page(context)

            print(f"Opening Carousell URL: {search_url}")

            response = await page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            print(f"Current URL: {page.url}")

            if response is not None:
                print(f"HTTP status: {response.status}")
            else:
                print("HTTP status: No response")

            # Wait for the dynamic search page to load.
            await page.wait_for_timeout(6_000)

            await close_popups(page)

            # Scroll to trigger lazy-loaded listing cards.
            await page.mouse.wheel(0, 1_500)
            await page.wait_for_timeout(2_000)

            await page.mouse.wheel(0, -500)
            await page.wait_for_timeout(1_000)

            await save_debug_files(page)

            all_links = page.locator("a[href]")
            total_links = await all_links.count()

            print(f"Total links on page: {total_links}")

            listing_links = page.locator(
                'a[href*="/p/"]'
            )

            listing_link_count = await listing_links.count()

            print(
                "Possible listing links found: "
                f"{listing_link_count}"
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

                    # Remove tracking fragments when checking duplicates.
                    clean_url = full_url.split("?")[0]

                    if clean_url in seen_urls:
                        continue

                    seen_urls.add(clean_url)

                    link_text = ""

                    try:
                        link_text = (
                            await link.inner_text()
                        ).strip()
                    except Exception:
                        pass

                    card_text = await get_card_text(link)

                    combined_text = (
                        f"{link_text}\n{card_text}"
                    ).strip()

                    price = extract_price(combined_text)
                    posted_time = extract_posted_time(
                        combined_text
                    )

                    # Apply the maximum-price filter.
                    if max_price is not None:
                        if price is None:
                            continue

                        if price > max_price:
                            continue

                    title = choose_title(
                        link_text=link_text,
                        card_text=card_text,
                    )

                    listing_id_match = re.search(
                        r"-(\d+)(?:/)?$",
                        clean_url,
                    )

                    if listing_id_match:
                        listing_id = listing_id_match.group(1)
                    else:
                        listing_id = clean_url.rstrip("/").split("/")[-1]

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

                    print(
                        f"Added listing: {title} | "
                        f"{price} | {posted_time}"
                    )

                except Exception as error:
                    logger.warning(
                        "Skipped Carousell listing %s: %s",
                        index,
                        error,
                    )

            print(
                f"Carousell extraction completed: "
                f"{len(results)} listings"
            )

            return results

        except Exception as error:
            logger.exception(
                "Carousell search failed: %s",
                error,
            )

            try:
                if "page" in locals():
                    await save_debug_files(page)
            except Exception:
                pass

            raise

        finally:
            await context.close()