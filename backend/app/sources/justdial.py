import logging
import re
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_float, parse_int, slugify, to_soup

logger = logging.getLogger(__name__)

# JustDial renders phone digits as font-glyph spans. Best-effort decode map;
# decoded numbers are only accepted when they validate as real phone lengths.
GLYPH_TO_DIGIT = {
    "jcv": "0", "jcw": "1", "jcx": "2", "jcy": "3", "jc1": "4",
    "jc2": "5", "jc3": "6", "jc4": "7", "jc5": "8", "jc6": "9",
}


class JustDialSource(Source):
    """JustDial local-business directory — strongest coverage for Indian niches."""

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

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        url = f"https://www.justdial.com/{slugify(city)}/{slugify(niche)}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

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

    async def health(self) -> dict:
        html = await fetch_html("https://www.justdial.com/Delhi/Dentists", timeout=10.0)
        return {"source": self.name, "available": bool(html), "note": None}
