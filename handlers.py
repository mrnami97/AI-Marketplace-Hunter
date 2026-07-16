import html
import time
from types import SimpleNamespace

from telegram import Update
from telegram.ext import ContextTypes

from database import (
    add_watch,
    count_seen_listings,
    get_crawler_health,
    get_market_prices,
    get_market_stats,
    get_latest_watch,
    get_seen_listings,
    get_watch,
    get_watches,
    remove_watch as db_remove_watch,
)
from marketplace_search import (
    search_marketplace_groups,
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
from matching.matcher import product_key
from watcher import check_one_watch
from ai.analyzer import ai_analyzer
from ai.formatter import format_ai_results
from config import settings
from database import count_ai_cache


WELCOME = """
🤖 AI Marketplace Hunter v0.4.2

Results are split into:
• 15 Carousell
• 15 Facebook Kota Kinabalu
• 15 Facebook Kuala Lumpur

/search RTX 3070 under RM1200 cheapest
/search RTX 3070 under RM1200 newest
/search RTX 3070 under RM1200 best

/watch RTX 3070 under RM1200
/list
/remove 1
/current
/check 1
/status
""".strip()


def extract_sort_mode(
    raw: str,
) -> tuple[str, str]:
    words = raw.strip().split()

    if (
        words
        and words[-1].lower()
        in {
            "best",
            "newest",
            "cheapest",
        }
    ):
        return (
            " ".join(words[:-1]),
            words[-1].lower(),
        )

    return raw, "best"


def build_group_message(
    heading: str,
    listings: list,
    query: str,
    sort_mode: str,
) -> str | None:
    scored = sort_scored(
        score_listings(
            listings,
            query,
        ),
        sort_mode,
    )[:15]

    if not scored:
        return None

    rows = [
        f"<b>{html.escape(heading)}</b>",
        f"Sort: <b>{html.escape(sort_mode.title())}</b>",
        "",
        "<pre>",
        "#  Price    Age       AI",
        "---------------------------",
    ]

    links = []

    for index, scored_item in enumerate(
        scored,
        start=1,
    ):
        listing = scored_item.listing

        price = (
            f"RM{listing.price:,.0f}"
            if listing.price is not None
            else "Unknown"
        )

        age = short_age(
            listing.posted_text
        )

        rows.append(
            f"{index:<2} "
            f"{price:<8} "
            f"{age:<9} "
            f"{score_emoji(scored_item.score)}"
            f"{scored_item.score}"
        )

        safe_url = html.escape(
            listing.url,
            quote=True,
        )

        safe_title = html.escape(
            listing.title[:58]
        )

        location = html.escape(
            listing.location
            or "Not shown"
        )

        links.append(
            f'{index}. '
            f'<a href="{safe_url}">'
            f'Click Here</a> — '
            f'{safe_title} '
            f'[{location}]'
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


def build_progress_message(
    query: str,
    percentage: int,
    detail: str,
) -> str:
    percentage = max(
        0,
        min(100, percentage),
    )

    filled = round(
        percentage / 5
    )

    bar = (
        "█" * filled
        + "░" * (20 - filled)
    )

    if percentage < 10:
        carousell_status = "⏳ Waiting"
        kk_status = "⏳ Waiting"
        kl_status = "⏳ Waiting"

    elif percentage < 35:
        carousell_status = "🔄 Searching"
        kk_status = "⏳ Waiting"
        kl_status = "⏳ Waiting"

    elif percentage < 40:
        carousell_status = "✅ Completed"
        kk_status = "⏳ Waiting"
        kl_status = "⏳ Waiting"

    elif percentage < 65:
        carousell_status = "✅ Completed"
        kk_status = "🔄 Searching"
        kl_status = "⏳ Waiting"

    elif percentage < 90:
        carousell_status = "✅ Completed"
        kk_status = "✅ Completed"
        kl_status = "🔄 Searching"

    else:
        carousell_status = "✅ Completed"
        kk_status = "✅ Completed"
        kl_status = "✅ Completed"

    return (
        f"🔎 <b>Searching {html.escape(query)}</b>\n\n"
        f"<code>{bar}</code> "
        f"<b>{percentage}%</b>\n\n"
        f"🟠 Carousell: {carousell_status}\n"
        f"🔵 Facebook Kota Kinabalu: "
        f"{kk_status}\n"
        f"🔵 Facebook Kuala Lumpur: "
        f"{kl_status}\n\n"
        f"ℹ️ {html.escape(detail)}"
    )


class TelegramProgressUpdater:
    def __init__(
        self,
        message,
        query: str,
    ) -> None:
        self.message = message
        self.query = query
        self.last_percentage = -1
        self.last_update_time = 0.0
        self.last_text = ""

    async def update(
        self,
        percentage: int,
        detail: str,
    ) -> None:
        now = time.monotonic()

        # Avoid Telegram edit-rate limits while still keeping the display live.
        should_update = (
            percentage >= 100
            or percentage - self.last_percentage >= 3
            or now - self.last_update_time >= 2.0
        )

        if not should_update:
            return

        text = build_progress_message(
            query=self.query,
            percentage=percentage,
            detail=detail,
        )

        if text == self.last_text:
            return

        try:
            await self.message.edit_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            self.last_percentage = percentage
            self.last_update_time = now
            self.last_text = text

        except Exception:
            # A progress update must never stop the actual marketplace search.
            pass


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.message.reply_text(
        WELCOME
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await update.message.reply_text(
        WELCOME
    )


async def search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    raw = " ".join(
        context.args
    ).strip()

    if not raw:
        await update.message.reply_text(
            "Usage:\n"
            "/search RTX 3070 "
            "under RM1200 cheapest"
        )
        return

    cleaned_raw, sort_mode = (
        extract_sort_mode(raw)
    )

    request = parse_request(
        cleaned_raw
    )

    status_message = (
        await update.message.reply_text(
            build_progress_message(
                query=request.query,
                percentage=0,
                detail="Waiting to start",
            ),
            parse_mode="HTML",
        )
    )

    progress = TelegramProgressUpdater(
        message=status_message,
        query=request.query,
    )

    try:
        grouped = await search_marketplace_groups(
            query=request.query,
            max_price=request.max_price,
            location=None,
            progress_callback=progress.update,
        )

        await progress.update(
            100,
            "Preparing Telegram result tables",
        )
        await status_message.delete()

        groups = [
            (
                "🟠 Carousell — Up to 15",
                grouped.carousell,
            ),
            (
                "🔵 Facebook Kota Kinabalu — Up to 15",
                grouped.facebook_kota_kinabalu,
            ),
            (
                "🔵 Facebook Kuala Lumpur — Up to 15",
                grouped.facebook_kuala_lumpur,
            ),
        ]

        sent_any = False

        for heading, listings in groups:
            message = build_group_message(
                heading=heading,
                listings=listings,
                query=request.query,
                sort_mode=sort_mode,
            )

            if message is None:
                await update.message.reply_text(
                    f"{heading}\n\n"
                    "No matching listings found."
                )
                continue

            sent_any = True

            await update.message.reply_text(
                message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

        if not sent_any:
            await update.message.reply_text(
                "No matching listings found "
                "from any source."
            )
            return

        combined=[]
        for source_items in [grouped.carousell,grouped.facebook_kota_kinabalu,grouped.facebook_kuala_lumpur]:
            combined.extend(score_listings(source_items,request.query))
        combined=sort_scored(combined,"best")
        if settings.ai_enabled and settings.ai_api_key and combined:
            ai_status=await update.message.reply_text("🤖 Analysing the best shortlisted listings...")
            ai_results = await ai_analyzer.analyze_top(
                query=request.query,
                scored_listings=combined,
            )
            await ai_status.delete()
            if ai_results:
                await update.message.reply_text(format_ai_results(request.query,ai_results),parse_mode="HTML",disable_web_page_preview=True)

    except Exception as error:
        print(
            f"Search error: {error}"
        )

        await status_message.edit_text(
            "❌ Marketplace search failed.\n"
            "Check the VS Code terminal."
        )


async def watch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    raw = " ".join(
        context.args
    ).strip()

    if not raw:
        await update.message.reply_text(
            "Usage:\n"
            "/watch RTX 3070 "
            "under RM1200"
        )
        return

    request = parse_request(raw)

    watch_id = add_watch(
        chat_id=update.effective_chat.id,
        query=request.query,
        max_price=request.max_price,
        location=None,
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
        "This watch checks:\n"
        "• Carousell\n"
        "• Facebook Kota Kinabalu\n"
        "• Facebook Kuala Lumpur"
    )


async def list_watches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_watches(
        update.effective_chat.id
    )

    if not watches:
        await update.message.reply_text(
            "No watchlists yet."
        )
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

        rows.append(
            f"{item['id']:<3} "
            f"{query:<19} "
            f"{price}"
        )

    rows.append("</pre>")

    await update.message.reply_text(
        "\n".join(rows),
        parse_mode="HTML",
    )


async def remove_watch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        not context.args
        or not context.args[0].isdigit()
    ):
        await update.message.reply_text(
            "Usage:\n/remove 1"
        )
        return

    watch_id = int(
        context.args[0]
    )

    deleted = db_remove_watch(
        update.effective_chat.id,
        watch_id,
    )

    await update.message.reply_text(
        f"🗑 Watch #{watch_id} removed."
        if deleted
        else (
            f"Watch #{watch_id} "
            "was not found."
        )
    )


async def current_listings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id
    args = list(context.args)
    sort_mode = "best"

    if (
        args
        and args[-1].lower()
        in {
            "best",
            "newest",
            "cheapest",
        }
    ):
        sort_mode = args.pop().lower()

    if args and args[0].isdigit():
        watch_item = get_watch(
            chat_id,
            int(args[0]),
        )
    else:
        watch_item = get_latest_watch(
            chat_id
        )

    if watch_item is None:
        await update.message.reply_text(
            "No watch found."
        )
        return

    rows = get_seen_listings(
        watch_id=int(watch_item["id"]),
        limit=100,
    )

    grouped = {
        "Carousell": [],
        "Facebook Kota Kinabalu": [],
        "Facebook Kuala Lumpur": [],
    }

    for row in rows:
        title = (
            row["title"]
            or "Unknown listing"
        )

        if is_blocked_listing(
            title,
            watch_item["query"],
        ):
            continue

        listing = SimpleNamespace(
            source=row["source"],
            listing_id=row["listing_id"],
            title=title,
            price=row["price"],
            url=row["url"],
            posted_text=row["posted_text"],
            location=row["location"],
        )

        if row["source"] == "Carousell":
            if (
                posted_age_minutes(
                    row["posted_text"]
                ) > 30 * 24 * 60
            ):
                continue

            grouped["Carousell"].append(
                listing
            )

        elif (
            row["location"]
            and "kota kinabalu"
            in row["location"].lower()
        ):
            grouped[
                "Facebook Kota Kinabalu"
            ].append(listing)

        else:
            grouped[
                "Facebook Kuala Lumpur"
            ].append(listing)

    for heading, listings in grouped.items():
        message = build_group_message(
            heading=heading,
            listings=listings,
            query=watch_item["query"],
            sort_mode=sort_mode,
        )

        if message:
            await update.message.reply_text(
                message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )


async def manual_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = update.effective_chat.id

    if (
        context.args
        and context.args[0].isdigit()
    ):
        watch_item = get_watch(
            chat_id,
            int(context.args[0]),
        )
    else:
        watch_item = get_latest_watch(
            chat_id
        )

    if watch_item is None:
        await update.message.reply_text(
            "Watch not found."
        )
        return

    status_message = (
        await update.message.reply_text(
            f"🔄 Checking Watch "
            f"#{watch_item['id']}..."
        )
    )

    try:
        result = await check_one_watch(
            bot=context.bot,
            watch=watch_item,
            send_initial_message=False,
        )

        await status_message.edit_text(
            "✅ Check completed\n\n"
            f"Listings: "
            f"{result['total_found']}\n"
            f"New listings: "
            f"{result['new_found']}"
        )

    except Exception as error:
        print(
            f"Manual check error: {error}"
        )

        await status_message.edit_text(
            "❌ Check failed."
        )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    watches = get_watches(
        update.effective_chat.id
    )

    lines = [
        "🤖 <b>AI Marketplace Hunter</b>",
        "",
        "Version: v0.4.2",
        "Status: Running ✅",
        "Results per search:",
        "• 15 Carousell",
        "• 15 Facebook Kota Kinabalu",
        "• 15 Facebook Kuala Lumpur",
        "Scheduler: Every 5 minutes",
        (
            "Active watches: "
            f"{sum(1 for item in watches if item['active'])}"
        ),
        "",
    ]

    for item in watches:
        lines.extend(
            [
                (
                    f"<b>Watch #{item['id']} — "
                    f"{html.escape(item['query'])}"
                    "</b>"
                ),
                (
                    "Saved: "
                    f"{count_seen_listings(int(item['id']))}"
                ),
                (
                    "Last check: "
                    f"{html.escape(item['last_checked_at'] or 'Not checked')}"
                ),
                "",
            ]
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query=" ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage:\n/history RTX 3070")
        return
    key=product_key(query)
    stats=get_market_stats(key)
    rows=get_market_prices(key,200)
    if not rows:
        await update.message.reply_text("No history yet. Run /search first.")
        return
    values=sorted(float(r["price"]) for r in rows)
    n=len(values); median=(values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2)
    await update.message.reply_text(
        f"📈 <b>{html.escape(query)}</b>\n\nSamples: {int(stats['samples'])}\nMedian: RM{median:,.0f}\nAverage: RM{float(stats['average_price']):,.0f}\nLowest: RM{float(stats['minimum_price']):,.0f}\nHighest: RM{float(stats['maximum_price']):,.0f}",
        parse_mode="HTML",
    )

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows=get_crawler_health()
    if not rows:
        await update.message.reply_text("No health data yet. Run /search first.")
        return
    lines=["🩺 <b>Crawler Health</b>",""]
    for row in rows:
        icon="✅" if row['status']=='healthy' else "⚠️"
        lines += [f"<b>{icon} {html.escape(row['source'])}</b>",f"Results: {int(row['results_found'])}",f"Last update: {html.escape(row['updated_at'])}",""]
    await update.message.reply_text("\n".join(lines),parse_mode="HTML")


async def ai_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    configured=settings.ai_enabled and bool(settings.ai_api_key)
    available=configured and ai_analyzer.runtime_available
    await update.message.reply_text(
        "\n".join([
            "🤖 <b>AI Status</b>", "",
            "Configured: "+("Yes ✅" if configured else "No"),
            "Runtime access: "+("Available ✅" if available else "Unavailable ⚠️"),
            "Provider: PIKKAPI Responses API",
            f"Base URL: {html.escape(settings.ai_base_url)}",
            f"Model: {html.escape(settings.ai_model)}",
            f"Status: {html.escape(ai_analyzer.runtime_reason)}",
            f"Maximum analyses/search: {settings.ai_max_listings_per_search}",
            f"Cached analyses: {count_ai_cache()}",
            "", "Local marketplace scoring continues if PIKKAPI is unavailable.",
        ]), parse_mode="HTML")


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw=" ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Usage:\n/analyze iPhone 15 Pro under RM3000"); return
    if not settings.ai_enabled or not settings.ai_api_key:
        await update.message.reply_text("AI is disabled. Set AI_ENABLED=true and GEMINI_API_KEY in .env."); return
    request=parse_request(raw); status=await update.message.reply_text("🔎 Collecting and locally shortlisting listings...")
    grouped=await search_marketplace_groups(query=request.query,max_price=request.max_price,location=None)
    scored=[]
    for source_items in [grouped.carousell,grouped.facebook_kota_kinabalu,grouped.facebook_kuala_lumpur]: scored.extend(score_listings(source_items,request.query))
    scored=sort_scored(scored,"best"); await status.edit_text("🤖 Running AI analysis...")
    results = await ai_analyzer.analyze_top(
        query=request.query,
        scored_listings=scored,
    )
    await status.delete()
    if not results: await update.message.reply_text("No suitable listings found."); return
    await update.message.reply_text(format_ai_results(request.query,results),parse_mode="HTML",disable_web_page_preview=True)
