import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_float, parse_int, slugify, to_soup

logger = logging.getLogger(__name__)

# JustDial renders phone digits as font-glyph spans. Best-effort decode map;
# decoded numbers are only accepted when they validate as real phone lengths.
GLYPH_TO_DIGIT = {
    "jcv": "0", "jcw": "1", "jcx": "2", "jcy": "3", "jc1": "4",
    "jc2": "5", "jc3": "6", "jc4": "7", "jc5": "8", "jc6": "9",
}

#: The desktop host answers every request with a 14-byte stub, so the
#: desktop URL could never return a listing. The mobile host serves the
#: full page.
WAP_HOST = "https://wap.justdial.com"

#: Explains, in one line, why this adapter cannot currently return leads.
CLIENT_SIDE_NOTE = (
    "listings are loaded by a client-side XHR - the server-rendered HTML has "
    "no listing markup, and JustDial geo-resolves the city from the request "
    "IP (a /Pune/ URL still returns Mumbai). Needs a browser engine."
)


class JustDialSource(Source):
    """JustDial local-business directory - strongest coverage for Indian niches.

    JustDial is the best-fitting directory for this product's ICP, but it
    renders its listing grid client-side. The mobile host does serve the
    page (about 800 KB, including a ``__NEXT_DATA__`` blob with the
    pagination state), yet the listing array itself only ever arrives over
    XHR from a private endpoint that is not derivable from the page shell.

    Rather than returning an empty list that looks like "Pune has no
    dentists", this adapter says so, and :meth:`health` reports the same
    thing - so the operator can see which sources are actually working
    instead of trusting a "multi-source" claim.
    """

    name = "justdial"
    supports_india = True
    supports_global = False

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return bool(niche and area)

    def _decode_phone(self, card) -> Optional[str]:
        try:
            holder = card.select_one(".mobilesv, .jcn, .callcontent")
            if holder is None:
                return None
            digits = []
            for span in holder.find_all("span"):
                classes = " ".join(span.get("class", []) or [])
                match = re.search(r"\bjc(\w)\b", classes)
                if match:
                    digit = GLYPH_TO_DIGIT.get(f"jc{match.group(1)}")
                    if digit:
                        digits.append(digit)
            number = "".join(digits)
            return number if 10 <= len(number) <= 12 else None
        except Exception:
            return None

    def _parse_cards(self, soup, niche: str, area: str, limit: int) -> List[RawLead]:
        """Parses server-rendered listing cards, if the site ever serves them."""
        cards = soup.select("li.cntre, section.cntre, div.cntre") or soup.select("li.result")
        if not cards:
            return []

        leads: List[RawLead] = []
        for card in cards[:limit]:
            try:
                name_el = card.select_one(".lng_commn_name, h2 span, h3 span") or card.select_one("h2, h3")
                name = name_el.get_text(" ", strip=True) if name_el else ""
                if not name:
                    continue

                address_el = card.select_one(".lng_add, .cont_sw_addr, .address")
                rating_el = card.select_one(".green_box, .rt-sect, .rating")
                votes_el = card.select_one(".rt_count, .votes")
                link_el = card.select_one("a[href*='/'], a.comp-text, a.website")

                website = None
                if link_el:
                    href = link_el.get("href", "")
                    if href.startswith("http"):
                        website = href

                leads.append(
                    raw_lead(
                        name=name.split(" - ")[0].strip(),
                        website=website,
                        phone=self._decode_phone(card),
                        address=address_el.get_text(" ", strip=True) if address_el else None,
                        rating=parse_float(rating_el.get_text() if rating_el else None),
                        reviews_count=parse_int(votes_el.get_text() if votes_el else None),
                        industry=niche.title(),
                        source=self.name,
                        query=self.build_query(niche, area),
                    )
                )
            except Exception as e:
                logger.debug(f"[justdial] card parse error: {e}")
                continue

        return leads

    @staticmethod
    def _next_data(html: str) -> Optional[Dict[str, Any]]:
        match = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        url = f"{WAP_HOST}/{slugify(city)}/{slugify(niche)}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

        leads = self._parse_cards(soup, niche, area, limit)
        if leads:
            self._last_note = None
            return leads

        # The shell loaded but carried no listings. Say why, precisely.
        data = self._next_data(html) or {}
        page_props = (data.get("props") or {}).get("pageProps") or {}
        resolved_city = page_props.get("city")
        note = CLIENT_SIDE_NOTE
        if resolved_city and resolved_city.lower() != city.lower():
            note += f" (resolved city was '{resolved_city}', not '{city}')"
        return self._failed(note)

    async def health(self) -> dict:
        url = f"{WAP_HOST}/Delhi/Dentists"
        html = await fetch_html(url, timeout=10.0)
        if not html:
            return {"source": self.name, "available": False, "note": "could not fetch"}
        soup = to_soup(html)
        cards = soup.select("li.cntre, section.cntre, div.cntre, li.result") if soup else []
        if cards:
            return {"source": self.name, "available": True, "note": None}
        return {"source": self.name, "available": False, "note": CLIENT_SIDE_NOTE}
