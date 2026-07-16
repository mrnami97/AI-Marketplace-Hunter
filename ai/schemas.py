from typing import Literal

from pydantic import BaseModel, Field


class ListingAIAnalysis(BaseModel):
    is_relevant: bool
    category: str
    normalized_product_name: str
    match_confidence: int = Field(
        ge=0,
        le=100,
    )
    is_complete_item: bool
    condition: str
    scam_risk: Literal[
        "low",
        "medium",
        "high",
    ]
    deal_score: int = Field(
        ge=0,
        le=100,
    )
    fair_price_low: float | None = None
    fair_price_high: float | None = None
    red_flags: list[str] = []
    positive_signals: list[str] = []
    seller_questions: list[str] = []
    negotiation_tip: str
    summary: str
