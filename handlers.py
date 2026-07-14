from telegram import Update
from telegram.ext import ContextTypes

from crawler.carousell import search_carousell
from database import (
    add_watch,
    count_seen_listings,
    get_latest_watch,
    get_seen_listings,
    get_watch,
    get_watches,
    remove_watch as db_remove_watch,
)
from parser import parse_request
from watcher import check_one_watch


WELCOME = """
🤖 AI Marketplace Hunter

Commands:
/search RTX 3070 under RM1200
/watch RTX 3070 under RM1200
/list
/remove 1
/current
/current 2
/check
/check 2
/status
/help
""".strip()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.message.reply_text(WELCOME)


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.message.reply_text(WELCOME)


async def search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    raw = " ".join(context.args).strip()

    if not raw:
        await update.message.reply_text(
            "Usage:\n/search RTX 3070 under RM1200"
        )
        return

    request = parse_request(raw)

    status_message = await update.message.reply_text(
        f"🔎 Searching Carousell for:\n{request.query}"
    )

    try:
        listings = await search_carousell(
            query=request.query,
            max_price=request.max_price,
            max_results=8,
        )

        if not listings:
            await status_message.edit_text(
                "No matching Carousell listings found."
            )
            return

        await status_message.edit_text(
            f"✅ Found {len(listings)} Carousell listings"
        )

        for number, listing in enumerate(listings, start=1):
            price = (
                f"RM{listing.price:,.0f}"
                if listing.price is not None
                else "Price not detected"
            )
            posted = listing.posted_text or "Posted time not detected"

            message = (
                f"#{number} — {listing.title}\n\n"
                f"💰 {price}\n"
                f"🕒 Posted: {posted}\n"
                f"🌐 Carousell\n\n"
                f"🔗 {listing.url}"
            )

            await update.message.reply_text(
                message,
                disable_web_page_preview=True,
            )

    except Exception as error:
        print(f"Search error: {error}")
        await status_message.edit_text(
            "❌ Carousell search failed.\n"
            "Check the VS Code terminal for the error."
        )


async def watch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    raw = " ".join(context.args).strip()

    if not raw:
        await update.message.reply_text(
            "Usage:\n/watch RTX 3070 under RM1200"
        )
        return

    request = parse_request(raw)

    watch_id = add_watch(
        chat_id=update.effective_chat.id,
        query=request.query,
        max_price=request.max_price,
        location=request.location,
    )

    price_text = (
        f"RM{request.max_price:,.0f}"
        if request.max_price is not None
        else "No maximum"
    )

    await update.message.reply_text(
        f"✅ Watch saved\n\n"
        f"ID: {watch_id}\n"
        f"Item: {request.query}\n"
        f"Maximum price: {price_text}\n"
        f"Location: {request.location or 'Any'}\n\n"
        "The automatic watcher will initialize it shortly."
    )


async def list_watches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_watches(update.effective_chat.id)

    if not watches:
        await update.message.reply_text("No watchlists yet.")
        return

    lines = ["👀 Your watchlists\n"]

    for item in watches:
        price = (
            f"RM{item['max_price']:,.0f}"
            if item["max_price"] is not None
            else "Any price"
        )
        state = "Active" if item["active"] else "Paused"

        lines.append(
            f"#{item['id']} — {item['query']}\n"
            f"Price: {price} | Status: {state}\n"
        )

    await update.message.reply_text("\n".join(lines))


async def remove_watch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage:\n/remove 1")
        return

    watch_id = int(context.args[0])
    deleted = db_remove_watch(
        update.effective_chat.id,
        watch_id,
    )

    if deleted:
        await update.message.reply_text(
            f"🗑 Watch #{watch_id} removed."
        )
    else:
        await update.message.reply_text(
            f"Watch #{watch_id} was not found."
        )


async def current_listings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id

    if context.args and context.args[0].isdigit():
        watch_item = get_watch(chat_id, int(context.args[0]))
    else:
        watch_item = get_latest_watch(chat_id)

    if watch_item is None:
        await update.message.reply_text(
            "No watch found.\n\n"
            "Create one first:\n"
            "/watch RTX 3070 under RM1200"
        )
        return

    listings = get_seen_listings(
        watch_id=int(watch_item["id"]),
        limit=15,
    )

    if not listings:
        await update.message.reply_text(
            f"Watch #{watch_item['id']} has no saved listings yet.\n\n"
            f"Run /check {watch_item['id']} first."
        )
        return

    await update.message.reply_text(
        f"📦 Current saved listings\n\n"
        f"Watch #{watch_item['id']}: {watch_item['query']}\n"
        f"Showing {len(listings)} listings"
    )

    for number, listing in enumerate(listings, start=1):
        price = (
            f"RM{listing['price']:,.0f}"
            if listing["price"] is not None
            else "Price not detected"
        )
        posted = listing["posted_text"] or "Posted time not detected"

        message = (
            f"#{number} — {listing['title']}\n\n"
            f"💰 {price}\n"
            f"🕒 Posted: {posted}\n"
            f"🌐 {listing['source']}\n\n"
            f"🔗 {listing['url']}"
        )

        await update.message.reply_text(
            message,
            disable_web_page_preview=True,
        )


async def manual_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id

    if context.args and context.args[0].isdigit():
        watch_item = get_watch(chat_id, int(context.args[0]))
    else:
        watch_item = get_latest_watch(chat_id)

    if watch_item is None:
        await update.message.reply_text(
            "Watch not found.\n\nUsage:\n/check 2"
        )
        return

    status_message = await update.message.reply_text(
        f"🔄 Checking Watch #{watch_item['id']}...\n"
        f"Item: {watch_item['query']}"
    )

    try:
        result = await check_one_watch(
            bot=context.bot,
            watch=watch_item,
            send_initial_message=False,
        )

        await status_message.edit_text(
            f"✅ Check completed\n\n"
            f"Watch #{result['watch_id']}: {watch_item['query']}\n\n"
            f"Listings found: {result['total_found']}\n"
            f"New listings: {result['new_found']}"
        )

    except Exception as error:
        print(f"Manual check error: {error}")
        await status_message.edit_text(
            "❌ Check failed.\n"
            "See the VS Code terminal for details."
        )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id
    watches = get_watches(chat_id)

    if not watches:
        await update.message.reply_text(
            "🤖 AI Marketplace Hunter\n\n"
            "Status: Running ✅\n"
            "Active watches: 0"
        )
        return

    active_count = sum(
        1 for item in watches if bool(item["active"])
    )

    lines = [
        "🤖 AI Marketplace Hunter",
        "",
        "Status: Running ✅",
        "Scheduler: Every 5 minutes",
        f"Active watches: {active_count}",
        "",
    ]

    for item in watches:
        total_seen = count_seen_listings(int(item["id"]))
        state = "Active ✅" if item["active"] else "Paused ⏸"
        initialized = "Yes" if item["initialized"] else "No"
        last_checked = item["last_checked_at"] or "Not checked yet"
        price = (
            f"RM{item['max_price']:,.0f}"
            if item["max_price"] is not None
            else "Any price"
        )

        lines.extend(
            [
                f"Watch #{item['id']} — {item['query']}",
                f"Status: {state}",
                f"Maximum price: {price}",
                f"Initialized: {initialized}",
                f"Listings saved: {total_seen}",
                f"Last check: {last_checked}",
                "",
            ]
        )

    await update.message.reply_text("\n".join(lines))
