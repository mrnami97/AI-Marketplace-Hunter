import html
from typing import Any


def _read_result_item(
    item: Any,
):
    """
    Support the current AIListingResult dataclass and older dictionary-shaped
    cache/formatter results.
    """
    if isinstance(item, dict):
        return (
            item["listing"],
            item["analysis"],
            bool(item.get("cached")),
        )

    return (
        item.listing,
        item.analysis,
        bool(item.cached),
    )


def format_ai_results(
    query: str,
    results: list,
) -> str:
    lines = [
        (
            "🤖 <b>DeepSeek Analysis — "
            f"{html.escape(query)}</b>"
        ),
        "",
    ]

    for index, item in enumerate(
        results,
        start=1,
    ):
        (
            listing,
            analysis,
            cached,
        ) = _read_result_item(item)

        price = (
            f"RM{listing.price:,.0f}"
            if listing.price is not None
            else "Unknown"
        )

        risk_icon = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🔴",
        }.get(
            analysis.scam_risk,
            "⚪",
        )

        url = html.escape(
            listing.url,
            quote=True,
        )

        lines.extend(
            [
                (
                    f"<b>{index}. "
                    f"{html.escape(analysis.normalized_product_name)}</b>"
                ),
                (
                    f"💰 {price} · "
                    f"{html.escape(listing.source)}"
                ),
                (
                    "🎯 Match: "
                    f"{analysis.match_confidence}%"
                ),
                (
                    "🔥 AI deal score: "
                    f"{analysis.deal_score}/100"
                ),
                (
                    f"{risk_icon} Risk: "
                    f"{analysis.scam_risk.title()}"
                ),
                (
                    "📦 Complete item: "
                    + (
                        "Yes"
                        if analysis.is_complete_item
                        else "No / uncertain"
                    )
                ),
                (
                    "🧾 Condition: "
                    f"{html.escape(analysis.condition)}"
                ),
                (
                    "💬 "
                    f"{html.escape(analysis.summary)}"
                ),
            ]
        )

        if analysis.red_flags:
            lines.append(
                "⚠️ "
                + html.escape(
                    "; ".join(
                        analysis.red_flags[:3]
                    )
                )
            )

        if analysis.negotiation_tip:
            lines.append(
                "🤝 "
                + html.escape(
                    analysis.negotiation_tip
                )
            )

        lines.extend(
            [
                (
                    f'<a href="{url}">'
                    "Open Listing</a>"
                ),
                (
                    f"<i>{'Cached' if cached else 'New'} "
                    "analysis</i>"
                ),
                "",
            ]
        )

    return "\n".join(lines)
