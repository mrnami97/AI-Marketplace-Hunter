import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import Page, sync_playwright


SEARCH_TERM = "RTX 3070"
MAX_RESULTS = 10

BASE_URL = "https://www.carousell.com.my"
PROFILE_FOLDER = Path(__file__).parent / "playwright-profile"


def close_popups(page: Page) -> None:
    """Close common Carousell popups when they appear."""

    possible_buttons = [
        'button[aria-label="Close"]',
        'button:has-text("Close")',
        'button:has-text("Skip")',
        'button:has-text("Got it")',
    ]

    for selector in possible_buttons:
        try:
            button = page.locator(selector).first

            if button.is_visible(timeout=1_000):
                button.click()
                page.wait_for_timeout(500)
        except Exception:
            continue

    # The safety popup shown in your screenshot has an X button.
    try:
        popup = page.get_by_text("Buy safely on Carousell", exact=False)

        if popup.is_visible(timeout=1_000):
            popup_container = popup.locator("xpath=ancestor::*[@role='dialog'][1]")

            if popup_container.count() > 0:
                close_button = popup_container.locator("button").first

                if close_button.is_visible():
                    close_button.click()
                    page.wait_for_timeout(500)
    except Exception:
        pass


def parse_price(text: str) -> str | None:
    match = re.search(r"\bRM\s?[\d,]+(?:\.\d{1,2})?", text, re.IGNORECASE)

    if match:
        return match.group(0).replace("RM ", "RM")

    return None


def parse_posted_time(text: str) -> str | None:
    patterns = [
        r"\b\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago\b",
        r"\bjust now\b",
        r"\btoday\b",
        r"\byesterday\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return match.group(0)

    return None


def clean_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def extract_listings(page: Page) -> list[dict]:
    listing_links = page.locator('a[href*="/p/"]')
    total_links = listing_links.count()

    print(f"Found {total_links} possible listing links.")

    results: list[dict] = []
    seen_urls: set[str] = set()

    for index in range(total_links):
        link = listing_links.nth(index)

        try:
            href = link.get_attribute("href")

            if not href:
                continue

            full_url = urljoin(BASE_URL, href)

            if full_url in seen_urls:
                continue

            seen_urls.add(full_url)

            # Move upwards until we find a useful listing-card container.
            card = link

            for _ in range(6):
                parent = card.locator("xpath=..")

                if parent.count() == 0:
                    break

                parent_text = parent.inner_text().strip()

                if len(parent_text) >= 20:
                    card = parent

                if parse_price(parent_text) and parse_posted_time(parent_text):
                    card = parent
                    break

                card = parent

            card_text = card.inner_text().strip()
            lines = clean_lines(card_text)

            price = parse_price(card_text)
            posted_time = parse_posted_time(card_text)

            title = None

            for line in lines:
                if line == price or line == posted_time:
                    continue

                if re.fullmatch(r"RM[\d,]+(?:\.\d{1,2})?", line):
                    continue

                if len(line) >= 8:
                    title = line
                    break

            if not title:
                title = link.inner_text().strip() or "Unknown title"

            results.append(
                {
                    "title": title,
                    "price": price or "Price not detected",
                    "posted_time": posted_time or "Posted time not detected",
                    "url": full_url,
                    "raw_text": card_text[:600],
                }
            )

            if len(results) >= MAX_RESULTS:
                break

        except Exception as error:
            print(f"Skipped one listing: {error}")

    return results


def main() -> None:
    search_url = (
        f"{BASE_URL}/search/"
        f"{quote_plus(SEARCH_TERM)}"
    )

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_FOLDER.resolve()),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()

        print(f"Opening: {search_url}")

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        page.wait_for_timeout(5_000)

        close_popups(page)

        # Scroll down slightly so more cards are loaded.
        page.mouse.wheel(0, 1_500)
        page.wait_for_timeout(3_000)

        listings = extract_listings(page)

        print("\n" + "=" * 70)
        print(f"EXTRACTED {len(listings)} LISTINGS")
        print("=" * 70)

        for number, listing in enumerate(listings, start=1):
            print(f"\nListing #{number}")
            print(f"Title: {listing['title']}")
            print(f"Price: {listing['price']}")
            print(f"Posted: {listing['posted_time']}")
            print(f"URL: {listing['url']}")
            print("-" * 70)

        input("\nPress Enter to close the browser...")

        context.close()


if __name__ == "__main__":
    main()