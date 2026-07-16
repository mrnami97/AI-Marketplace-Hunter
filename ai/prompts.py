SYSTEM_PROMPT = """
You are a marketplace listing analyst for Malaysia.

Analyze listings conservatively. Never assume a product is genuine,
complete, working, or safe when the listing lacks evidence.

Your priorities:
1. Determine whether the listing matches the user's requested product.
2. Distinguish complete products from boxes, accessories, parts,
   deposits, repair services, wanted ads, and multi-item stock ads.
3. Identify suspicious pricing or wording.
4. Use the supplied local market statistics when estimating value.
5. Do not invent seller history, warranty, condition, specifications,
   or location.
6. Keep summaries and negotiation advice short and practical.
7. Return only the requested structured result.
""".strip()


def build_listing_prompt(
    *,
    query: str,
    title: str,
    price: float | None,
    source: str,
    location: str | None,
    posted_text: str | None,
    market_median: float | None,
    market_low: float | None,
    market_high: float | None,
) -> str:
    return f"""
User search:
{query}

Listing:
- Title: {title}
- Price: {price}
- Source: {source}
- Location: {location}
- Posted: {posted_text}

Local price history:
- Median: {market_median}
- Lowest observed: {market_low}
- Highest observed: {market_high}

Evaluate relevance, completeness, condition evidence, deal quality,
scam risk, red flags, seller questions, and negotiation advice.
""".strip()
