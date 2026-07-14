import math
import re
from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable


BLOCKED_PHRASES = {
    "empty box",
    "box only",
    "kotak sahaja",
    "kotak saja",
    "kotak only",
    "for parts",
    "spare parts",
    "broken",
    "faulty",
    "needs repair",
    "repair only",
    "fan only",
    "replacement fan",
    "gpu fan replacement",
    "cooler only",
    "heatsink only",
    "pcb only",
    "wanted to buy",
    "want to buy",
    "wtb",
    "deposit only",
    "reservation fee",
    "backplate only",
    "waterblock only",
    "water block only",
}

ACCESSORY_WORDS = {
    "fan", "cooler", "heatsink", "backplate",
    "waterblock", "water block", "pcb", "box", "kotak",
}

ACCESSORY_INTENT_WORDS = {
    "only", "replacement", "replace", "compatible",
    "compatibility", "spare", "part", "parts",
    "accessory", "accessories",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "with", "for", "under", "below",
    "in", "at", "near", "used", "new", "gpu", "graphics", "card",
}

GPU_MODEL_PATTERN = re.compile(
    r"\b(?:rtx|gtx|rx|arc)?\s*"
    r"(?:10[567]0|16[056]0|20[678]0|30[5689]0|3070|3080|3090|"
    r"40[6789]0|50[789]0|5[567]00|6[56789]00|7[6789]00|"
    r"a[357]80|a[357]50|a770|b570|b580)"
    r"(?:\s*ti|\s*super|\s*xt|\s*gre|\s*s)?\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ScoredListing:
    listing: Any
    score: int
    relevance_score: int
    freshness_score: int
    price_score: int
    risk: str
    verdict: str
    age_minutes: int


def normalize_text(text: str) -> str:
    value = text.lower()
    value = value.replace("-", " ")
    value = value.replace("_", " ")
    value = value.replace("/", " / ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact_model_text(text: str) -> str:
    value = re.sub(r"[^a-z0-9]", "", text.lower())

    # Common marketplace abbreviations.
    value = re.sub(r"(20[678]0|30[678]0|40[678]0)s\b", r"\1super", value)
    value = value.replace("sup", "super")

    return value


def query_terms(query: str) -> list[str]:
    normalized = normalize_text(query)
    parts = re.findall(r"[a-z0-9]+", normalized)

    return [
        part
        for part in parts
        if part not in STOP_WORDS and len(part) >= 2
    ]


def canonicalize_model(model: str) -> str:
    value = compact_model_text(model)
    value = re.sub(r"^(rtx|gtx|rx|arc)", "", value)

    # Treat 2070S and 2070 Super as the same model.
    value = re.sub(r"^(20[678]0|30[678]0|40[678]0)s$", r"\1super", value)

    return value


def extract_gpu_models(text: str) -> set[str]:
    models = set()

    for match in GPU_MODEL_PATTERN.finditer(text):
        model = canonicalize_model(match.group(0))
        if model:
            models.add(model)

    # Catch compact forms such as RTX2070S.
    compact = compact_model_text(text)
    compact_matches = re.findall(
        r"(?:rtx|gtx|rx|arc)?"
        r"(20[678]0|30[5689]0|40[6789]0)"
        r"(ti|super|s)?",
        compact,
    )

    for number, suffix in compact_matches:
        canonical_suffix = "super" if suffix == "s" else suffix
        models.add(f"{number}{canonical_suffix}")

    return models


def query_gpu_models(query: str) -> set[str]:
    return extract_gpu_models(query)


def has_exact_query_model(title: str, query: str) -> bool:
    wanted = query_gpu_models(query)
    found = extract_gpu_models(title)

    if not wanted:
        return True

    return bool(wanted.intersection(found))


def is_multi_model_ad(title: str, query: str) -> bool:
    title_models = extract_gpu_models(title)
    wanted_models = query_gpu_models(query)
    unrelated_models = title_models - wanted_models

    return len(title_models) >= 5 or len(unrelated_models) >= 4


def is_blocked_listing(title: str, query: str = "") -> bool:
    normalized = normalize_text(title)

    if any(phrase in normalized for phrase in BLOCKED_PHRASES):
        return True

    words = set(re.findall(r"[a-z0-9]+", normalized))
    accessory_present = bool(words.intersection(ACCESSORY_WORDS))
    accessory_intent = bool(words.intersection(ACCESSORY_INTENT_WORDS))
    exact_model = has_exact_query_model(title, query)

    if accessory_present and accessory_intent:
        return True

    if accessory_present and query and not exact_model:
        return True

    if query and is_multi_model_ad(title, query) and accessory_present:
        return True

    return False


def relevance_score(title: str, query: str) -> int:
    wanted_models = query_gpu_models(query)
    title_models = extract_gpu_models(title)

    if wanted_models:
        if not wanted_models.intersection(title_models):
            return 0

        unrelated = title_models - wanted_models

        if len(unrelated) >= 4:
            return 45
        if len(unrelated) == 3:
            return 60
        if len(unrelated) == 2:
            return 72
        if len(unrelated) == 1:
            return 82

    terms = query_terms(query)

    if not terms:
        return 60

    normalized_title = normalize_text(title)
    compact_title = compact_model_text(title)

    matched = sum(
        1
        for term in terms
        if term in normalized_title
        or compact_model_text(term) in compact_title
        or (
            term == "super"
            and re.search(r"(20[678]0|30[678]0|40[678]0)s\b", compact_title)
        )
    )

    ratio = matched / len(terms)
    score = int(ratio * 80)

    if wanted_models:
        score += 20

    return max(0, min(score, 100))


def posted_age_minutes(posted_text: str | None) -> int:
    if not posted_text:
        return 10**9

    text = normalize_text(posted_text)

    if "just now" in text:
        return 0
    if text == "today":
        return 12 * 60
    if text == "yesterday":
        return 24 * 60

    match = re.search(
        r"(\d+)\s+"
        r"(minute|minutes|hour|hours|day|days|week|weeks|"
        r"month|months|year|years)\s+ago",
        text,
    )

    if not match:
        return 10**9

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "minute": 1,
        "minutes": 1,
        "hour": 60,
        "hours": 60,
        "day": 24 * 60,
        "days": 24 * 60,
        "week": 7 * 24 * 60,
        "weeks": 7 * 24 * 60,
        "month": 30 * 24 * 60,
        "months": 30 * 24 * 60,
        "year": 365 * 24 * 60,
        "years": 365 * 24 * 60,
    }

    return value * multipliers[unit]


def freshness_score_from_minutes(age_minutes: int) -> int:
    if age_minutes <= 10:
        return 100
    if age_minutes <= 60:
        return 95
    if age_minutes <= 6 * 60:
        return 88
    if age_minutes <= 24 * 60:
        return 80
    if age_minutes <= 3 * 24 * 60:
        return 68
    if age_minutes <= 7 * 24 * 60:
        return 55
    if age_minutes <= 14 * 24 * 60:
        return 40
    if age_minutes <= 30 * 24 * 60:
        return 25
    return 0


def logical_price_bounds(
    listings: list[Any],
) -> tuple[float | None, float | None]:
    prices = sorted(
        float(item.price)
        for item in listings
        if getattr(item, "price", None) is not None
        and float(item.price) >= 100
    )

    # Do not over-filter small searches.
    if len(prices) < 6:
        return None, None

    start = max(0, len(prices) // 5)
    typical_prices = prices[start:]
    typical = median(typical_prices)

    # Wider lower bound to keep genuine bargains.
    lower = max(100.0, typical * 0.35)
    upper = typical * 2.50

    return lower, upper


def filter_logical_prices(listings: list[Any]) -> list[Any]:
    lower, upper = logical_price_bounds(listings)

    if lower is None or upper is None:
        return listings

    return [
        listing
        for listing in listings
        if getattr(listing, "price", None) is not None
        and lower <= float(listing.price) <= upper
    ]


def calculate_price_score(
    price: float | None,
    comparison_prices: Iterable[float],
) -> int:
    if price is None:
        return 20

    values = sorted(value for value in comparison_prices if value > 0)

    if not values:
        return 60

    typical = median(values)

    if typical <= 0:
        return 60

    ratio = price / typical

    if ratio < 0.35:
        return 10
    if ratio <= 0.60:
        return 85
    if ratio <= 0.80:
        return 100
    if ratio <= 0.95:
        return 90
    if ratio <= 1.10:
        return 75
    if ratio <= 1.35:
        return 50
    return 25


def score_listings(listings: list[Any], query: str) -> list[ScoredListing]:
    logical_listings = filter_logical_prices(listings)

    prices = [
        float(item.price)
        for item in logical_listings
        if getattr(item, "price", None) is not None
    ]

    scored = []

    for listing in logical_listings:
        title = getattr(listing, "title", "") or ""

        if is_blocked_listing(title, query):
            continue

        relevance = relevance_score(title, query)

        # Reduced from 70 to 60 to avoid hiding valid abbreviations.
        if relevance < 60:
            continue

        age_minutes = posted_age_minutes(
            getattr(listing, "posted_text", None)
        )
        freshness = freshness_score_from_minutes(age_minutes)
        price = calculate_price_score(
            getattr(listing, "price", None),
            prices,
        )

        final_score = round(
            relevance * 0.50
            + freshness * 0.30
            + price * 0.20
        )

        if final_score >= 90:
            verdict = "Excellent"
            risk = "Low"
        elif final_score >= 80:
            verdict = "Good"
            risk = "Low"
        elif final_score >= 65:
            verdict = "Fair"
            risk = "Medium"
        else:
            verdict = "Skip"
            risk = "High"

        scored.append(
            ScoredListing(
                listing=listing,
                score=final_score,
                relevance_score=relevance,
                freshness_score=freshness,
                price_score=price,
                risk=risk,
                verdict=verdict,
                age_minutes=age_minutes,
            )
        )

    return scored


def sort_scored(
    items: list[ScoredListing],
    sort_mode: str,
) -> list[ScoredListing]:
    if sort_mode == "cheapest":
        return sorted(
            items,
            key=lambda item: (
                item.listing.price is None,
                item.listing.price
                if item.listing.price is not None
                else math.inf,
                item.age_minutes,
            ),
        )

    if sort_mode == "newest":
        return sorted(
            items,
            key=lambda item: (
                item.age_minutes,
                -item.score,
            ),
        )

    return sorted(
        items,
        key=lambda item: (
            -item.score,
            item.age_minutes,
        ),
    )


def score_emoji(score: int) -> str:
    if score >= 90:
        return "🟢"
    if score >= 80:
        return "🟡"
    if score >= 65:
        return "🟠"
    return "🔴"


def short_age(posted_text: str | None) -> str:
    if not posted_text:
        return "Unknown"

    replacements = {
        "minutes ago": "min",
        "minute ago": "min",
        "hours ago": "hr",
        "hour ago": "hr",
        "days ago": "day",
        "day ago": "day",
        "weeks ago": "wk",
        "week ago": "wk",
        "months ago": "mo",
        "month ago": "mo",
        "years ago": "yr",
        "year ago": "yr",
    }

    result = posted_text

    for old, new in replacements.items():
        result = result.replace(old, new)

    return result[:10]
