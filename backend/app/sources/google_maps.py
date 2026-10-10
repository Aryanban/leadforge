import logging
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from app.scraper.maps_http import scrape_google_maps_http
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

        # HTTP first: one request returns ~20 fully-populated places (name,
        # phone, website, rating, lat/lng, address) in well under a second, and
        # the viewport sweep widens that to `limit`. Playwright needs a browser
        # launch plus an unreliable scroll loop to reach the same 20, so it is
        # the fallback, not the default.
        try:
            raw = await scrape_google_maps_http(query, max_results=limit)
        except Exception as e:
            logger.warning(f"[google_maps] HTTP path error: {e}; falling back to Playwright")
            raw = []

        if not raw:
            try:
                raw = await scrape_google_maps_playwright(query, limit)
            except Exception as e:
                logger.warning(f"[google_maps] Playwright error: {e}")
                raw = []

        if not raw:
            try:
                raw = await scrape_google_http_fallback(query, limit)
            except Exception as e:
                return self._failed(f"all Google Maps paths failed: {e}")

        # A permanently closed clinic is not a lead - it cannot be sold to.
        dropped_closed = sum(1 for lead in raw if lead.get("is_closed"))
        if dropped_closed:
            logger.info(f"[google_maps] dropped {dropped_closed} closed place(s) for '{query}'")

        return [
            raw_lead(
                name=lead.get("name", "").strip(),
                website=lead.get("website") or None,
                phone=lead.get("phone") or None,
                address=lead.get("address") or None,
                rating=lead.get("rating"),
                reviews_count=lead.get("reviews_count"),
                industry=lead.get("industry") or niche,
                place_id=lead.get("place_id") or lead.get("google_data_id"),
                maps_url=lead.get("maps_url") or None,
                latitude=lead.get("latitude"),
                longitude=lead.get("longitude"),
                is_claimed=lead.get("is_claimed", True),
                operational_status=lead.get("operational_status") or ("closed" if lead.get("is_closed") else None),
                price_tier=lead.get("price_tier"),
                source=self.name,
                query=query,
            )
            for lead in raw
            if lead.get("name", "").strip() and not lead.get("is_closed")
        ]
