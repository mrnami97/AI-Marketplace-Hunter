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
    "fan",
    "cooler",
    "heatsink",
    "backplate",
    "waterblock",
    "pcb",
    "box",
    "kotak",
}

ACCESSORY_INTENT_WORDS = {
    "only",
    "replacement",
    "replace",
    "compatible",
    "compatibility",
    "spare",
    "part",
    "parts",
    "accessory",
    "accessories",
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "with", "for", "under", "below",
    "in", "at", "near", "used", "new", "gpu", "graphics", "card",
}

GPU_MODEL_PATTERN = re.compile(
    r"\b(?P<brand>rtx|gtx|rx|arc)?\s*"
    r"(?P<number>"
    r"10[567]0|16[056]0|20[678]0|30[5689]0|3070|3080|3090|"
    r"40[6789]0|50[789]0|5[567]00|6[56789]00|7[6789]00|"
    r"a[357]80|a[357]50|a770|b570|b580"
    r")"
    r"(?P<suffix>\s*ti|\s*super|\s*xt|\s*gre|\s*s)?\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ModelToken:
    brand: str
    number: str
    suffix: str


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
    value = re.sub(
        r"(20[678]0|30[678]0|40[678]0)s\b",
        r"\1super",
        value,
    )
    return value.replace("sup", "super")


def _canonical_suffix(value: str) -> str:
    suffix = re.sub(r"\s+", "", value.lower())

    if suffix == "s":
        return "super"

    return suffix


def extract_model_tokens(text: str) -> list[ModelToken]:
    tokens: list[ModelToken] = []

    for match in GPU_MODEL_PATTERN.finditer(text):
        tokens.append(
            ModelToken(
                brand=(match.group("brand") or "").lower(),
                number=match.group("number").lower(),
                suffix=_canonical_suffix(
                    match.group("suffix") or ""
                ),
            )
        )

    compact = compact_model_text(text)

    compact_pattern = re.compile(
        r"(?P<brand>rtx|gtx|rx|arc)?"
        r"(?P<number>"
        r"10[567]0|16[056]0|20[678]0|30[5689]0|3070|3080|3090|"
        r"40[6789]0|50[789]0|5[567]00|6[56789]00|7[6789]00|"
        r"a[357]80|a[357]50|a770|b570|b580"
        r")"
        r"(?P<suffix>ti|super|s|xt|gre)?"
    )

    for match in compact_pattern.finditer(compact):
        token = ModelToken(
            brand=(match.group("brand") or "").lower(),
            number=match.group("number").lower(),
            suffix=_canonical_suffix(
                match.group("suffix") or ""
            ),
        )

        if token not in tokens:
            tokens.append(token)

    return tokens


def model_matches_query(
    title: str,
    query: str,
) -> bool:
    """
    Match only the requested GPU family.

    Examples:
    - Query RTX 3070 accepts RTX 3070 and RTX 3070 Ti.
    - Query RTX 3070 Ti requires RTX 3070 Ti.
    - Query GTX 1660 accepts GTX 1660 and GTX 1660 Super/Ti.
    - RTX 3070 search does not accept GTX 1660, RTX 3060 or RTX 3080.

    This is matching logic, not a global blacklist. Searching for GTX 1660
    later will still return GTX 1660 listings normally.
    """
    query_tokens = extract_model_tokens(query)

    if not query_tokens:
        return True

    title_tokens = extract_model_tokens(title)

    if not title_tokens:
        return False

    for wanted in query_tokens:
        for found in title_tokens:
            if wanted.number != found.number:
                continue

            if wanted.brand and found.brand and wanted.brand != found.brand:
                continue

            # A query with a specific suffix requires that exact suffix.
            if wanted.suffix:
                if wanted.suffix != found.suffix:
                    continue

            # A query without a suffix accepts the base family and variants.
            return True

    return False


def is_blocked_listing(
    title: str,
    query: str = "",
) -> bool:
    normalized = normalize_text(title)

    if any(
        phrase in normalized
        for phrase in BLOCKED_PHRASES
    ):
        return True

    # The title must match the requested model family.
    if query and not model_matches_query(
        title,
        query,
    ):
        return True

    words = set(
        re.findall(
            r"[a-z0-9]+",
            normalized,
        )
    )

    accessory_present = bool(
        words.intersection(
            ACCESSORY_WORDS
        )
    )

    accessory_intent = bool(
        words.intersection(
            ACCESSORY_INTENT_WORDS
        )
    )

    if (
        accessory_present
        and accessory_intent
    ):
        return True

    return False


def query_terms(query: str) -> list[str]:
    parts = re.findall(
        r"[a-z0-9]+",
        normalize_text(query),
    )

    return [
        part
        for part in parts
        if part not in STOP_WORDS
        and len(part) >= 2
    ]


def relevance_score(
    title: str,
    query: str,
) -> int:
    if not model_matches_query(
        title,
        query,
    ):
        return 0

    query_tokens = extract_model_tokens(query)
    title_tokens = extract_model_tokens(title)

    score = 70

    if query_tokens:
        wanted = query_tokens[0]

        exact_suffix_match = any(
            token.number == wanted.number
            and (
                not wanted.brand
                or not token.brand
                or token.brand == wanted.brand
            )
            and token.suffix == wanted.suffix
            for token in title_tokens
        )

        same_family_variant = any(
            token.number == wanted.number
            and (
                not wanted.brand
                or not token.brand
                or token.brand == wanted.brand
            )
            for token in title_tokens
        )

        if exact_suffix_match:
            score = 100
        elif same_family_variant:
            score = 90

    terms = query_terms(query)
    normalized_title = normalize_text(title)
    compact_title = compact_model_text(title)

    non_model_terms = [
        term
        for term in terms
        if not any(
            term in {
                token.brand,
                token.number,
                token.suffix,
            }
            for token in query_tokens
        )
    ]

    if non_model_terms:
        matched = sum(
            1
            for term in non_model_terms
            if term in normalized_title
            or compact_model_text(term)
            in compact_title
        )

        score += round(
            10 * matched
            / len(non_model_terms)
        )

    return max(
        0,
        min(score, 100),
    )


def posted_age_minutes(
    posted_text: str | None,
) -> int:
    if not posted_text:
        return 10**9

    text = normalize_text(posted_text)

    if (
        "just now" in text
        or "just listed" in text
    ):
        return 0

    if text == "today":
        return 12 * 60

    if text == "yesterday":
        return 24 * 60

    match = re.search(
        r"(?:listed\s+)?(\d+)\s+"
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


def freshness_score_from_minutes(
    age_minutes: int,
) -> int:
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
) -> tuple[
    float | None,
    float | None,
]:
    prices = sorted(
        float(item.price)
        for item in listings
        if getattr(
            item,
            "price",
            None,
        )
        is not None
        and float(item.price) >= 100
    )

    if len(prices) < 6:
        return None, None

    start = max(
        0,
        len(prices) // 5,
    )

    typical = median(
        prices[start:]
    )

    return (
        max(
            100.0,
            typical * 0.35,
        ),
        typical * 2.50,
    )


def filter_logical_prices(
    listings: list[Any],
) -> list[Any]:
    lower, upper = logical_price_bounds(
        listings
    )

    if (
        lower is None
        or upper is None
    ):
        return listings

    return [
        listing
        for listing in listings
        if getattr(
            listing,
            "price",
            None,
        )
        is not None
        and lower
        <= float(listing.price)
        <= upper
    ]


def calculate_price_score(
    price: float | None,
    comparison_prices: Iterable[float],
) -> int:
    if price is None:
        return 20

    values = sorted(
        value
        for value in comparison_prices
        if value > 0
    )

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


def score_listings(
    listings: list[Any],
    query: str,
) -> list[ScoredListing]:
    matching_listings = [
        listing
        for listing in listings
        if not is_blocked_listing(
            getattr(
                listing,
                "title",
                "",
            )
            or "",
            query,
        )
    ]

    logical_listings = filter_logical_prices(
        matching_listings
    )

    prices = [
        float(item.price)
        for item in logical_listings
        if getattr(
            item,
            "price",
            None,
        )
        is not None
    ]

    scored: list[ScoredListing] = []

    for listing in logical_listings:
        title = (
            getattr(
                listing,
                "title",
                "",
            )
            or ""
        )

        relevance = relevance_score(
            title,
            query,
        )

        if relevance < 80:
            continue

        age_minutes = posted_age_minutes(
            getattr(
                listing,
                "posted_text",
                None,
            )
        )

        freshness = (
            freshness_score_from_minutes(
                age_minutes
            )
        )

        price = calculate_price_score(
            getattr(
                listing,
                "price",
                None,
            ),
            prices,
        )

        final_score = round(
            relevance * 0.55
            + freshness * 0.25
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
                item.listing.price
                is None,
                (
                    item.listing.price
                    if item.listing.price
                    is not None
                    else math.inf
                ),
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


def short_age(
    posted_text: str | None,
) -> str:
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
        result = result.replace(
            old,
            new,
        )

    return result[:10]
