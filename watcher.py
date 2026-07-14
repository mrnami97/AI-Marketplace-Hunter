import asyncio
import logging

from telegram.ext import ContextTypes

from crawler.carousell import search_carousell
from database import (
    get_active_watches,
    listing_was_seen,
    mark_watch_initialized,
    save_seen_listing,
    update_watch_checked_time,
)


logger = logging.getLogger(__name__)


def format_alert(watch, listing) -> str:
    price = (
        f"RM{listing.price:,.0f}"
        if listing.price is not None
        else "Price not detected"
    )

    posted = listing.posted_text or "Posted time not detected"

    return (
        "🚨 NEW CAROUSELL LISTING\n\n"
        f"Watch #{watch['id']}: {watch['query']}\n\n"
        f"{listing.title}\n\n"
        f"💰 {price}\n"
        f"🕒 Posted: {posted}\n"
        f"🌐 Carousell\n\n"
        f"🔗 {listing.url}"
    )


async def check_all_watches(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_active_watches()

    if not watches:
        logger.info("No active watches.")
        return

    logger.info("Checking %s active watches.", len(watches))

    for watch in watches:
        watch_id = int(watch["id"])
        chat_id = int(watch["chat_id"])
        initialized = bool(watch["initialized"])

        try:
            logger.info(
                "Checking watch #%s: %s",
                watch_id,
                watch["query"],
            )

            listings = await search_carousell(
                query=watch["query"],
                max_price=watch["max_price"],
                max_results=15,
            )

            new_listings = []

            for listing in listings:
                already_seen = listing_was_seen(
                    watch_id=watch_id,
                    source=listing.source,
                    listing_id=listing.listing_id,
                )

                save_seen_listing(
                    watch_id=watch_id,
                    source=listing.source,
                    listing_id=listing.listing_id,
                    title=listing.title,
                    price=listing.price,
                    url=listing.url,
                    posted_text=listing.posted_text,
                )

                if initialized and not already_seen:
                    new_listings.append(listing)

            if not initialized:
                mark_watch_initialized(watch_id)

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ Watch #{watch_id} initialized\n\n"
                        f"Item: {watch['query']}\n"
                        f"Saved {len(listings)} existing listings.\n\n"
                        "Future new listings will trigger alerts."
                    ),
                )

            else:
                update_watch_checked_time(watch_id)

                for listing in new_listings:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=format_alert(watch, listing),
                        disable_web_page_preview=True,
                    )

                    # Avoid sending messages too quickly.
                    await asyncio.sleep(1)

                logger.info(
                    "Watch #%s found %s new listings.",
                    watch_id,
                    len(new_listings),
                )

        except Exception:
            logger.exception(
                "Failed to check watch #%s",
                watch_id,
            )