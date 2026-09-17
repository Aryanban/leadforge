import logging
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_int, slugify, to_soup

logger = logging.getLogger(__name__)


class IndiaMARTSource(Source):
    """IndiaMART supplier directory — B2B manufacturers, wholesalers and dealers."""

    name = "indiamart"
    supports_india = True
    supports_global = False

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return bool(niche and area)

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        params = f"kw={slugify(niche)}&city={slugify(city)}"
        url = f"https://www.indiamart.com/search.php?{params}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

        cards = soup.select("div.ls-card, div.r-cl, .card-block, .product-tpl") or soup.select(
            "div[data-catalog]")
        if not cards:
            return []

        leads: List[RawLead] = []
        for card in cards[:limit]:
            try:
                name_el = card.select_one(".lcname, .company-name, h2, h3, .name")
                name = name_el.get_text(" ", strip=True) if name_el else ""
                if not name:
                    continue

                address_el = card.select_one(".lcaddr, .location, .city, .address")
                phone_el = card.select_one(".livemsg, .pns, .callnow, [data-pns]")
                rating_el = card.select_one(".sr, .stars, .rating")

                leads.append(
                    raw_lead(
                        name=name.split(" - ")[0].strip(),
                        website=None,
                        phone=phone_el.get_text(" ", strip=True) if phone_el else None,
                        address=address_el.get_text(" ", strip=True) if address_el else None,
                        rating=None,
                        reviews_count=parse_int(rating_el.get_text() if rating_el else None),
                        industry=niche.title(),
                        source=self.name,
                        query=self.build_query(niche, area),
                    )
                )
            except Exception as e:
                logger.debug(f"[indiamart] card parse error: {e}")
                continue

        return leads

    async def health(self) -> dict:
        html = await fetch_html("https://www.indiamart.com/search.php?kw=dentists&city=delhi", timeout=10.0)
        return {"source": self.name, "available": bool(html), "note": None}
