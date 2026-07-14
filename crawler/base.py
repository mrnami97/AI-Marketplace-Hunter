from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Listing:
    source: str
    title: str
    price: Optional[float]
    location: Optional[str]
    posted_text: Optional[str]
    posted_at: Optional[datetime]
    url: str
    listing_id: str
