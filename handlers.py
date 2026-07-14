from crawler.carousell import search_carousell
from urllib.parse import quote_plus
from telegram import Update
from telegram.ext import ContextTypes

from database import add_watch, get_watches, remove_watch as db_remove_watch
from parser import parse_request

WELCOME = """
🤖 AI Marketplace Hunter

Commands:
/search RTX 3070 under RM900 in Sabah
/watch RTX 3070 under RM900 in Sabah
/list
/remove 1
/help

The first version creates direct marketplace searches and stores watchlists.
Posted-time extraction and automatic checking will be added in the crawler module.
""".strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            location = listing.location or "Location not shown"

            message = (
                f"#{number} — {listing.title}\n\n"
                f"💰 {price}\n"
                f"🕒 Posted: {posted}\n"
                f"📍 {location}\n"
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

        
async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text(
            "Usage:\n/watch RTX 3070 under RM900 in Sabah"
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
        f"Use /list to see watches."
    )

async def list_watches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    watches = get_watches(update.effective_chat.id)
    if not watches:
        await update.message.reply_text("No active watchlists yet.")
        return

    lines = ["👀 Your watchlists\n"]
    for item in watches:
        price = (
            f"RM{item['max_price']:,.0f}"
            if item["max_price"] is not None
            else "Any price"
        )
        location = item["location"] or "Any location"
        lines.append(
            f"#{item['id']} — {item['query']}\n"
            f"Price: {price} | Location: {location}\n"
        )

    await update.message.reply_text("\n".join(lines))

async def remove_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage:\n/remove 1")
        return

    watch_id = int(context.args[0])
    deleted = db_remove_watch(update.effective_chat.id, watch_id)

    if deleted:
        await update.message.reply_text(f"🗑 Watch #{watch_id} removed.")
    else:
        await update.message.reply_text(f"Watch #{watch_id} was not found.")
