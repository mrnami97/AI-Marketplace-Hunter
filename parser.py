import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class SearchRequest:
    query: str
    max_price: Optional[float] = None
    location: Optional[str] = None

_PRICE_PATTERNS = [
    r"(?:under|below|max|<)\s*(?:rm|myr)?\s*([\d,]+(?:\.\d+)?)",
    r"(?:rm|myr)\s*([\d,]+(?:\.\d+)?)\s*(?:or less|maximum|max)?",
]

def parse_request(text: str) -> SearchRequest:
    cleaned = " ".join(text.strip().split())
    max_price = None

    for pattern in _PRICE_PATTERNS:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            max_price = float(match.group(1).replace(",", ""))
            cleaned = (cleaned[:match.start()] + cleaned[match.end():]).strip()
            break

    location = None
    location_match = re.search(
        r"\b(?:in|at|near)\s+([A-Za-z][A-Za-z .'-]{1,40})$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if location_match:
        location = location_match.group(1).strip()
        cleaned = cleaned[:location_match.start()].strip()

    return SearchRequest(
        query=cleaned,
        max_price=max_price,
        location=location,
    )
