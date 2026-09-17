import logging
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from app.scraper.maps_scraper import (
    scrape_google_maps_playwright,
    scrape_google_http_fallback,
)

logger = logging.getLogger(__name__)


class GoogleMapsSource(Source):
    """Primary source: high-fidelity Google Maps Playwright scraper with search fallback."""

    name = "google_maps"
    supports_india = True
    supports_global = True

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return True

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        query = self.build_query(niche, area)
        raw: List[dict] = []

        try:
            raw = await scrape_google_maps_playwright(query, limit)
        except Exception as e:
            logger.warning(f"[google_maps] Playwright error: {e}; falling back to HTTP search")
            raw = []

        if not raw:
            try:
                raw = await scrape_google_http_fallback(query, limit)
            except Exception as e:
                return self._failed(f"both Playwright and HTTP fallback failed: {e}")

        return [
            raw_lead(
                name=lead.get("name", "").strip(),
                website=lead.get("website") or None,
                phone=lead.get("phone") or None,
                address=lead.get("address") or None,
                rating=lead.get("rating"),
                reviews_count=lead.get("reviews_count"),
                industry=lead.get("industry") or niche,
                place_id=lead.get("place_id"),
                maps_url=lead.get("maps_url") or None,
                latitude=lead.get("latitude"),
                longitude=lead.get("longitude"),
                is_claimed=lead.get("is_claimed", True),
                operational_status=lead.get("operational_status"),
                price_tier=lead.get("price_tier"),
                source=self.name,
                query=query,
            )
            for lead in raw
            if lead.get("name", "").strip()
        ]
