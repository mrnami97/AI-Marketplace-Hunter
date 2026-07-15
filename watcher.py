import asyncio
import html
import logging
from typing import Any

from telegram import Bot
from telegram.ext import ContextTypes

from database import (
    get_active_watches,
    listing_was_seen,
    mark_watch_initialized,
    save_seen_listing,
    update_watch_checked_time,
)
from marketplace_search import (
    search_all_marketplaces,
)
from marketplace_utils import (
    score_emoji,
    score_listings,
    sort_scored,
)


logger = logging.getLogger(__name__)


def format_alert(
    watch: Any,
    scored: Any,
) -> str:
    listing = scored.listing

    price = (
        f"RM{listing.price:,.0f}"
        if listing.price is not None
        else "Unknown"
    )

    posted = (
        listing.posted_text
        or "Not shown"
    )

    location = (
        listing.location
        or "Not shown"
    )

    return (
        "🚨 <b>NEW MARKETPLACE LISTING</b>\n\n"
        f"<b>{html.escape(listing.title)}</b>\n"
        f"🌐 {html.escape(listing.source)}\n"
        f"📍 {html.escape(location)}\n"
        f"💰 {price}\n"
        f"🕒 {html.escape(posted)}\n"
        f"⭐ {score_emoji(scored.score)} "
        f"{scored.score}/100 "
        f"({scored.verdict})\n\n"
        f'<a href="'
        f'{html.escape(listing.url, quote=True)}'
        f'">Click Here</a>'
    )


async def check_one_watch(
    bot: Bot,
    watch: Any,
    send_initial_message: bool = True,
) -> dict[str, int | bool]:
    watch_id = int(watch["id"])
    chat_id = int(watch["chat_id"])
    initialized = bool(
        watch["initialized"]
    )

    listings = await search_all_marketplaces(
        query=watch["query"],
        max_price=watch["max_price"],
        max_results=30,
        location=watch["location"],
    )

    scored_items = sort_scored(
        score_listings(
            listings,
            watch["query"],
        ),
        "best",
    )

    new_items = []

    for scored in scored_items:
        listing = scored.listing

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
            location=listing.location,
        )

        if (
            initialized
            and not already_seen
        ):
            new_items.append(scored)

    if not initialized:
        mark_watch_initialized(
            watch_id
        )

        if send_initial_message:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Watch #{watch_id} "
                    "initialized\n\n"
                    f"Item: {watch['query']}\n"
                    f"Location: "
                    f"{watch['location'] or 'KK + KL'}\n"
                    f"Saved {len(scored_items)} "
                    "filtered listings.\n\n"
                    "Future new listings from "
                    "Carousell and Facebook will "
                    "trigger alerts."
                ),
            )

    else:
        update_watch_checked_time(
            watch_id
        )

        for scored in new_items:
            await bot.send_message(
                chat_id=chat_id,
                text=format_alert(
                    watch,
                    scored,
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            await asyncio.sleep(1)

    return {
        "watch_id": watch_id,
        "total_found": len(scored_items),
        "new_found": len(new_items),
        "initialized_before_check": initialized,
    }


async def check_all_watches(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_active_watches()

    if not watches:
        logger.info(
            "No active watches."
        )
        return

    for watch in watches:
        try:
            result = await check_one_watch(
                bot=context.bot,
                watch=watch,
            )

            logger.info(
                "Watch #%s: %s listings, "
                "%s new.",
                result["watch_id"],
                result["total_found"],
                result["new_found"],
            )

        except Exception:
            logger.exception(
                "Failed to check watch #%s",
                watch["id"],
            )
