import asyncio
import hashlib
import logging
from dataclasses import dataclass
from statistics import median

from ai.client import AIClient, PikkAPIAuthError, PikkAPIUsageError
from ai.prompts import SYSTEM_PROMPT, build_listing_prompt
from ai.schemas import ListingAIAnalysis
from config import settings
from database import get_ai_cache, get_market_prices, save_ai_cache
from matching.matcher import product_key_from_query

logger=logging.getLogger(__name__)

@dataclass(frozen=True)
class AIListingResult:
    listing: object
    analysis: ListingAIAnalysis
    cached: bool

def _cache_key(query: str, listing) -> str:
    raw='|'.join([query.lower().strip(),str(listing.source),str(listing.listing_id),str(listing.title),str(listing.price),'pikkapi',settings.ai_model])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _market_stats(query: str):
    rows=get_market_prices(product_key_from_query(query),limit=200)
    values=sorted(float(r['price']) for r in rows if r['price'] is not None)
    return (median(values),values[0],values[-1]) if values else (None,None,None)

def _fallback_analysis(listing, match_score: int, deal_score: int) -> ListingAIAnalysis:
    return ListingAIAnalysis(
        is_relevant=True, category='unknown', normalized_product_name=listing.title,
        match_confidence=match_score, is_complete_item=True, condition='not confirmed',
        scam_risk='medium', deal_score=deal_score,
        red_flags=['AI analysis unavailable; verify details with seller'],
        positive_signals=[], seller_questions=[
            'Is the item fully working?',
            'Can you provide a current test video and serial number?',
            'Is the listed price for the complete item?',
        ], negotiation_tip='Verify condition before negotiating.',
        summary='Local scoring only because AI analysis was unavailable.',
    )

class MarketplaceAIAnalyzer:
    def __init__(self) -> None:
        self.enabled=settings.ai_enabled and bool(settings.ai_api_key)
        self.client=(AIClient(settings.ai_api_key,settings.ai_model,settings.ai_timeout_seconds,settings.ai_base_url) if self.enabled else None)
        self.semaphore=asyncio.Semaphore(max(1,settings.ai_concurrency))
        self.runtime_available=self.enabled
        self.runtime_reason='Ready' if self.enabled else 'AI disabled or PIKKAPI key missing'

    async def analyze(self, *, query: str, scored_listing) -> AIListingResult:
        listing=scored_listing.listing
        key=_cache_key(query,listing)
        cached=get_ai_cache(key)
        if cached is not None:
            try:
                return AIListingResult(listing,ListingAIAnalysis.model_validate_json(cached['analysis_json']),True)
            except Exception:
                logger.exception('Invalid AI cache row.')
        if not self.enabled or not self.runtime_available or self.client is None:
            return AIListingResult(listing,_fallback_analysis(listing,scored_listing.match_score,scored_listing.deal_score),False)
        med,low,high=_market_stats(query)
        prompt=build_listing_prompt(query=query,title=listing.title,price=listing.price,source=listing.source,location=listing.location,posted_text=listing.posted_text,market_median=med,market_low=low,market_high=high)
        try:
            async with self.semaphore:
                analysis=await asyncio.to_thread(self.client.analyze_structured,system_prompt=SYSTEM_PROMPT,user_prompt=prompt)
            save_ai_cache(cache_key=key,query=query,source=listing.source,listing_id=listing.listing_id,model=settings.ai_model,analysis_json=analysis.model_dump_json())
            return AIListingResult(listing,analysis,False)
        except PikkAPIAuthError:
            self.runtime_available=False; self.runtime_reason='PIKKAPI token rejected. Check PIKKAPI_API_KEY.'
            logger.warning(self.runtime_reason)
        except PikkAPIUsageError:
            self.runtime_available=False; self.runtime_reason='PIKKAPI plan, credits, or quota unavailable.'
            logger.warning(self.runtime_reason)
        except Exception as error:
            self.runtime_reason=f'Last PIKKAPI request failed: {type(error).__name__}'
            logger.exception('AI listing analysis failed.')
        return AIListingResult(listing,_fallback_analysis(listing,scored_listing.match_score,scored_listing.deal_score),False)

    async def analyze_top(self, *, query: str, scored_listings: list, limit: int|None=None) -> list[AIListingResult]:
        n=limit if limit is not None else settings.ai_max_listings_per_search
        shortlist=scored_listings[:max(0,n)]
        if not shortlist: return []
        first=await self.analyze(query=query,scored_listing=shortlist[0])
        if len(shortlist)==1: return [first]
        if not self.runtime_available:
            return [first,*[AIListingResult(x.listing,_fallback_analysis(x.listing,x.match_score,x.deal_score),False) for x in shortlist[1:]]]
        rest=await asyncio.gather(*[self.analyze(query=query,scored_listing=x) for x in shortlist[1:]])
        return [first,*rest]

ai_analyzer=MarketplaceAIAnalyzer()
