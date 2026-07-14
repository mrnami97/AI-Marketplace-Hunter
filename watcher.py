import asyncio
import logging
from typing import Any

from telegram import Bot
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
crawler_lock = asyncio.Lock()


def format_alert(watch: Any, listing: Any) -> str:
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


async def check_one_watch(
    bot: Bot,
    watch: Any,
    send_initial_message: bool = True,
) -> dict[str, int | bool]:
    watch_id = int(watch["id"])
    chat_id = int(watch["chat_id"])
    initialized = bool(watch["initialized"])

    async with crawler_lock:
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

        if send_initial_message:
            await bot.send_message(
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
            await bot.send_message(
                chat_id=chat_id,
                text=format_alert(watch, listing),
                disable_web_page_preview=True,
            )
            await asyncio.sleep(1)

    return {
        "watch_id": watch_id,
        "total_found": len(listings),
        "new_found": len(new_listings),
        "initialized_before_check": initialized,
    }


async def check_all_watches(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_active_watches()

    if not watches:
        logger.info("No active watches.")
        return

    logger.info("Checking %s active watches.", len(watches))

    for watch in watches:
        try:
            result = await check_one_watch(
                bot=context.bot,
                watch=watch,
            )
            logger.info(
                "Watch #%s: %s listings, %s new.",
                result["watch_id"],
                result["total_found"],
                result["new_found"],
            )
        except Exception:
            logger.exception("Failed to check watch #%s", watch["id"])
