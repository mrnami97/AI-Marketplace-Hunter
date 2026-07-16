import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from matching.matcher import product_key
from database import save_market_prices, update_crawler_health

from config import settings
from crawler.base import Listing
from crawler.carousell import (
    search_carousell,
)
from crawler.facebook import (
    search_facebook_marketplace,
)


logger = logging.getLogger(__name__)

search_lock = asyncio.Lock()

ProgressCallback = Callable[
    [int, str],
    Awaitable[None],
]


@dataclass
class MarketplaceSearchResult:
    carousell: list[Listing]
    facebook_kota_kinabalu: list[Listing]
    facebook_kuala_lumpur: list[Listing]

    @property
    def all_listings(self) -> list[Listing]:
        return [
            *self.carousell,
            *self.facebook_kota_kinabalu,
            *self.facebook_kuala_lumpur,
        ]


def _normalize_title(title: str) -> str:
    value = title.lower()
    value = value.replace("-", " ")
    value = re.sub(r"[^a-z0-9 ]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _deduplicate(
    listings: list[Listing],
) -> list[Listing]:
    seen_ids: set[tuple[str, str]] = set()
    seen_content: set[
        tuple[str, str, int | None, str]
    ] = set()

    output: list[Listing] = []

    for listing in listings:
        id_key = (
            listing.source,
            listing.listing_id,
        )

        content_key = (
            listing.source,
            _normalize_title(
                listing.title
            ),
            (
                int(round(listing.price))
                if listing.price is not None
                else None
            ),
            (
                listing.location.lower().strip()
                if listing.location
                else ""
            ),
        )

        if (
            id_key in seen_ids
            or content_key in seen_content
        ):
            continue

        seen_ids.add(id_key)
        seen_content.add(content_key)
        output.append(listing)

    return output


async def _emit_progress(
    callback: ProgressCallback | None,
    percentage: int,
    detail: str,
) -> None:
    if callback is None:
        return

    await callback(
        max(0, min(100, percentage)),
        detail,
    )


async def search_marketplace_groups(
    query: str,
    max_price: float | None = None,
    location: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> MarketplaceSearchResult:
    async with search_lock:
        carousell_results: list[Listing] = []
        facebook_results: list[Listing] = []

        await _emit_progress(
            progress_callback,
            5,
            "Preparing browser search",
        )

        await _emit_progress(
            progress_callback,
            10,
            "Searching Carousell",
        )

        try:
            carousell_results = await search_carousell(
                query=query,
                max_price=max_price,
                max_results=(
                    settings.carousell_results_limit
                ),
            )

            await _emit_progress(
                progress_callback,
                35,
                (
                    "Carousell completed: "
                    f"{len(carousell_results)} found"
                ),
            )

        except Exception:
            logger.exception(
                "Carousell search failed."
            )

            await _emit_progress(
                progress_callback,
                35,
                "Carousell search failed; continuing",
            )

        if settings.facebook_enabled:
            await _emit_progress(
                progress_callback,
                40,
                "Starting Facebook Marketplace",
            )

            try:
                facebook_results = (
                    await search_facebook_marketplace(
                        query=query,
                        max_price=max_price,
                        max_results=(
                            settings
                            .facebook_max_results_per_location
                        ),
                        location=location,
                        progress_callback=progress_callback,
                        progress_start=40,
                        progress_end=90,
                    )
                )

            except Exception:
                logger.exception(
                    "Facebook Marketplace "
                    "search failed."
                )

                await _emit_progress(
                    progress_callback,
                    90,
                    "Facebook search failed; continuing",
                )

        await _emit_progress(
            progress_callback,
            93,
            "Removing duplicates",
        )

        carousell_results = _deduplicate(
            carousell_results
        )

        facebook_results = _deduplicate(
            facebook_results
        )

        await _emit_progress(
            progress_callback,
            96,
            "Separating KK and Kuala Lumpur results",
        )

        facebook_kk = [
            item
            for item in facebook_results
            if (
                item.location
                and "kota kinabalu"
                in item.location.lower()
            )
        ][:settings.facebook_max_results_per_location]

        facebook_kl = [
            item
            for item in facebook_results
            if (
                item.location
                and (
                    "kuala lumpur"
                    in item.location.lower()
                    or "selangor"
                    in item.location.lower()
                    or "petaling jaya"
                    in item.location.lower()
                    or "shah alam"
                    in item.location.lower()
                )
            )
        ][:settings.facebook_max_results_per_location]

        result = MarketplaceSearchResult(
            carousell=carousell_results[
                :settings.carousell_results_limit
            ],
            facebook_kota_kinabalu=facebook_kk,
            facebook_kuala_lumpur=facebook_kl,
        )

        save_market_prices(
            product_key(query),
            result.all_listings,
        )

        update_crawler_health(
            "Carousell",
            "healthy" if result.carousell else "partial",
            len(result.carousell),
            "Recent-first search",
        )
        update_crawler_health(
            "Facebook Kota Kinabalu",
            "healthy" if result.facebook_kota_kinabalu else "partial",
            len(result.facebook_kota_kinabalu),
            "Virtual-scroll capture",
        )
        update_crawler_health(
            "Facebook Kuala Lumpur",
            "healthy" if result.facebook_kuala_lumpur else "partial",
            len(result.facebook_kuala_lumpur),
            "Virtual-scroll capture",
        )

        await _emit_progress(
            progress_callback,
            100,
            (
                "Search completed: "
                f"{len(result.all_listings)} results"
            ),
        )

        return result


async def search_all_marketplaces(
    query: str,
    max_price: float | None = None,
    max_results: int = 45,
    location: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[Listing]:
    grouped = await search_marketplace_groups(
        query=query,
        max_price=max_price,
        location=location,
        progress_callback=progress_callback,
    )

    return grouped.all_listings
