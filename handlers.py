import html
from types import SimpleNamespace

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
from marketplace_utils import (
    is_blocked_listing,
    posted_age_minutes,
    score_emoji,
    score_listings,
    short_age,
    sort_scored,
)
from parser import parse_request
from watcher import check_one_watch


WELCOME = """
🤖 AI Marketplace Hunter v0.2.2

/search RTX 3070 under RM1200 best
/search RTX 3070 under RM1200 newest
/search RTX 3070 under RM1200 cheapest
/watch RTX 3070 under RM1200
/list
/remove 1
/current
/current 2 newest
/current 2 cheapest
/current 2 best
/check 2
/status
""".strip()


def extract_sort_mode(raw: str) -> tuple[str, str]:
    words = raw.strip().split()

    if words and words[-1].lower() in {"best", "newest", "cheapest"}:
        return " ".join(words[:-1]), words[-1].lower()

    return raw, "best"


def build_summary_message(
    heading: str,
    scored_items: list,
    sort_mode: str,
) -> str:
    rows = [
        f"<b>{html.escape(heading)}</b>",
        f"Sort: <b>{html.escape(sort_mode.title())}</b>",
        "",
        "<pre>",
        "#  Price    Age       AI",
        "---------------------------",
    ]

    links = []

    for index, scored in enumerate(scored_items, start=1):
        listing = scored.listing
        price = (
            f"RM{listing.price:,.0f}"
            if listing.price is not None
            else "Unknown"
        )
        age = short_age(listing.posted_text)

        rows.append(
            f"{index:<2} {price:<8} {age:<9} "
            f"{score_emoji(scored.score)}{scored.score}"
        )

        safe_url = html.escape(listing.url, quote=True)
        safe_title = html.escape(listing.title[:55])
        links.append(
            f'{index}. <a href="{safe_url}">Click Here</a> — {safe_title}'
        )

    rows.extend(
        [
            "</pre>",
            "",
            "<b>Links</b>",
            *links,
        ]
    )

    return "\n".join(rows)


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
            "Usage:\n/search RTX 3070 under RM1200 best"
        )
        return

    cleaned_raw, sort_mode = extract_sort_mode(raw)
    request = parse_request(cleaned_raw)

    status_message = await update.message.reply_text(
        f"🔎 Searching Carousell for:\n{request.query}"
    )

    try:
        listings = await search_carousell(
            query=request.query,
            max_price=request.max_price,
            max_results=15,
        )

        scored = sort_scored(
            score_listings(listings, request.query),
            sort_mode,
        )

        if not scored:
            await status_message.edit_text(
                "No fresh matching listings found after filtering."
            )
            return

        await status_message.delete()

        await update.message.reply_text(
            build_summary_message(
                heading=f"🔍 {request.query} — {len(scored)} results",
                scored_items=scored,
                sort_mode=sort_mode,
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as error:
        print(f"Search error: {error}")
        await status_message.edit_text(
            "❌ Carousell search failed.\n"
            "Check the VS Code terminal."
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
        f"Maximum price: {price_text}\n\n"
        "It will initialize during the next check."
    )


async def list_watches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_watches(update.effective_chat.id)

    if not watches:
        await update.message.reply_text("No watchlists yet.")
        return

    rows = [
        "👀 <b>Your Watchlists</b>",
        "",
        "<pre>",
        "ID  Item                Max",
        "---------------------------",
    ]

    for item in watches:
        price = (
            f"RM{item['max_price']:,.0f}"
            if item["max_price"] is not None
            else "Any"
        )
        query = item["query"][:18]
        rows.append(f"{item['id']:<3} {query:<19} {price}")

    rows.append("</pre>")

    await update.message.reply_text(
        "\n".join(rows),
        parse_mode="HTML",
    )


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

    await update.message.reply_text(
        f"🗑 Watch #{watch_id} removed."
        if deleted
        else f"Watch #{watch_id} was not found."
    )


async def current_listings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id
    args = list(context.args)

    sort_mode = "best"
    if args and args[-1].lower() in {"best", "newest", "cheapest"}:
        sort_mode = args.pop().lower()

    if args and args[0].isdigit():
        watch_item = get_watch(chat_id, int(args[0]))
    else:
        watch_item = get_latest_watch(chat_id)

    if watch_item is None:
        await update.message.reply_text("No watch found.")
        return

    rows = get_seen_listings(
        watch_id=int(watch_item["id"]),
        limit=40,
    )

    listings = []
    for row in rows:
        if is_blocked_listing(row["title"] or ""):
            continue
        if posted_age_minutes(row["posted_text"]) > 30 * 24 * 60:
            continue

        listings.append(
            SimpleNamespace(
                source=row["source"],
                listing_id=row["listing_id"],
                title=row["title"] or "Unknown listing",
                price=row["price"],
                url=row["url"],
                posted_text=row["posted_text"],
            )
        )

    scored = sort_scored(
        score_listings(listings, watch_item["query"]),
        sort_mode,
    )[:15]

    if not scored:
        await update.message.reply_text(
            f"Watch #{watch_item['id']} has no fresh saved listings."
        )
        return

    await update.message.reply_text(
        build_summary_message(
            heading=(
                f"📦 Watch #{watch_item['id']} — "
                f"{watch_item['query']}"
            ),
            scored_items=scored,
            sort_mode=sort_mode,
        ),
        parse_mode="HTML",
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
        await update.message.reply_text("Watch not found.")
        return

    status_message = await update.message.reply_text(
        f"🔄 Checking Watch #{watch_item['id']}..."
    )

    try:
        result = await check_one_watch(
            bot=context.bot,
            watch=watch_item,
            send_initial_message=False,
        )

        await status_message.edit_text(
            f"✅ Check completed\n\n"
            f"Filtered listings: {result['total_found']}\n"
            f"New listings: {result['new_found']}"
        )

    except Exception as error:
        print(f"Manual check error: {error}")
        await status_message.edit_text("❌ Check failed.")


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_watches(update.effective_chat.id)

    lines = [
        "🤖 <b>AI Marketplace Hunter</b>",
        "",
        "Status: Running ✅",
        "Scheduler: Every 5 minutes",
        f"Active watches: {sum(1 for item in watches if item['active'])}",
        "",
    ]

    for item in watches:
        lines.extend(
            [
                f"<b>Watch #{item['id']} — "
                f"{html.escape(item['query'])}</b>",
                f"Saved: {count_seen_listings(int(item['id']))}",
                f"Last check: {html.escape(item['last_checked_at'] or 'Not checked')}",
                "",
            ]
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )
