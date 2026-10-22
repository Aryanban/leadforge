import logging
import re
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_int, slugify, to_soup

logger = logging.getLogger(__name__)

#: The URL that actually serves a page. `www.indiamart.com/search.php` 404s.
SEARCH_URL = "https://dir.indiamart.com/search.mp"

#: Explains why this adapter usually returns nothing.
CLIENT_SIDE_NOTE = (
    "IndiaMART's search results are client-side rendered - the served HTML "
    "only carries a handful of static promoted slots, so a keyword-matched "
    "supplier is all this adapter can return. Needs a browser engine for "
    "the full result set."
)

#: Words too generic to count as a niche match on their own.
_STOPWORDS = {
    "and", "the", "for", "with", "dealer", "dealers", "supplier", "suppliers",
    "manufacturer", "manufacturers", "wholesaler", "wholesalers", "trader",
    "traders", "service", "services", "shop", "store", "company", "firm",
}


class IndiaMARTSource(Source):
    """IndiaMART supplier directory - B2B manufacturers, wholesalers and dealers.

    IndiaMART is a *product* directory, so it is the right source for a
    manufacturing or wholesale ICP and the wrong one for a local service
    ICP. For a service niche ("dentists in Pune") it correctly returns
    nothing rather than manufacturing leads.
    """

    name = "indiamart"
    supports_india = True
    supports_global = False

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return bool(niche and area)

    @staticmethod
    def _niche_tokens(niche: str) -> List[str]:
        tokens = [
            t for t in re.split(r"[^a-z0-9]+", (niche or "").lower())
            if len(t) > 2 and t not in _STOPWORDS
        ]
        return tokens

    def _matches_niche(self, name: str, niche: str) -> bool:
        """Guards against India's static promoted slots leaking across queries.

        The served page carries the same four promoted suppliers whatever
        the query, so without this guard a search for "dentists" would
        return cotton-t-shirt manufacturers - the classic silent-garbage
        failure.
        """
        tokens = self._niche_tokens(niche)
        if not tokens:
            return False
        lowered = (name or "").lower()
        for token in tokens:
            if token in lowered:
                return True
            # "shirts" should match "t-shirt" and vice versa.
            stem = token.rstrip("s")
            if len(stem) > 3 and stem in lowered:
                return True
        return False

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        params = f"ss={slugify(niche)}&city={slugify(city)}"
        url = f"{SEARCH_URL}?{params}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

        cards = soup.select("section.staticListingWidget, div.staticListingWidget")
        if not cards:
            return self._failed(CLIENT_SIDE_NOTE)

        leads: List[RawLead] = []
        for card in cards:
            if len(leads) >= limit:
                break
            try:
                name_el = card.select_one("h2, h3")
                name = name_el.get_text(" ", strip=True) if name_el else ""
                if not name:
                    continue
                if not self._matches_niche(name, niche):
                    continue

                city_el = card.select_one(".staticSupplierBox strong, .staticSupplierBox")
                address = city_el.get_text(" ", strip=True) if city_el else None
                if address and city and city.lower() not in address.lower():
                    # A promoted slot from another city is not a local lead.
                    continue

                phone_el = card.select_one("[data-pns], .livemsg, .pns, .callnow")
                rating_el = card.select_one(".sr, .stars, .rating")

                leads.append(
                    raw_lead(
                        name=name.split(" - ")[0].strip(),
                        website=None,
                        phone=phone_el.get_text(" ", strip=True) if phone_el else None,
                        address=address,
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

        if not leads:
            return self._failed(
                f"no IndiaMART supplier matched '{niche}' in {city}. "
                + CLIENT_SIDE_NOTE
            )

        self._last_note = None
        return leads

    async def health(self) -> dict:
        url = f"{SEARCH_URL}?ss=steel-traders&city=delhi"
        html = await fetch_html(url, timeout=10.0)
        if not html:
            return {"source": self.name, "available": False, "note": "could not fetch"}
        soup = to_soup(html)
        cards = soup.select("section.staticListingWidget, div.staticListingWidget") if soup else []
        if cards:
            return {
                "source": self.name,
                "available": True,
                "note": "limited - only static promoted slots are server-rendered",
            }
        return {"source": self.name, "available": False, "note": CLIENT_SIDE_NOTE}
