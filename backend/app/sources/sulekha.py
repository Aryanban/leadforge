import logging
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_float, parse_int, slugify, to_soup

logger = logging.getLogger(__name__)


class SulekhaSource(Source):
    """Sulekha services directory — strong for local services and home professionals."""

    name = "sulekha"
    supports_india = True
    supports_global = False

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return bool(niche and area)

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        url = f"https://www.sulekha.com/{slugify(niche)}/{slugify(city)}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

        cards = soup.select("li.biz-listing, div.biz-card, .service-providers li, .list-item")
        if not cards:
            return []

        leads: List[RawLead] = []
        for card in cards[:limit]:
            try:
                name_el = card.select_one("h2, h3, .biz-name, .title")
                name = name_el.get_text(" ", strip=True) if name_el else ""
                if not name:
                    continue

                address_el = card.select_one(".address, .location, .area")
                rating_el = card.select_one(".rating, .stars, .rate")
                reviews_el = card.select_one(".reviews, .review-count")
                phone_el = card.select_one(".phone, .contact, .call")

                leads.append(
                    raw_lead(
                        name=name.split(" - ")[0].strip(),
                        website=None,
                        phone=phone_el.get_text(" ", strip=True) if phone_el else None,
                        address=address_el.get_text(" ", strip=True) if address_el else None,
                        rating=parse_float(rating_el.get_text() if rating_el else None),
                        reviews_count=parse_int(reviews_el.get_text() if reviews_el else None),
                        industry=niche.title(),
                        source=self.name,
                        query=self.build_query(niche, area),
                    )
                )
            except Exception as e:
                logger.debug(f"[sulekha] card parse error: {e}")
                continue

        return leads

    async def health(self) -> dict:
        html = await fetch_html("https://www.sulekha.com/dentists/delhi", timeout=10.0)
        return {"source": self.name, "available": bool(html), "note": None}
