import logging
import re
from typing import List, Optional

from .base import RawLead, Source, raw_lead
from .http_utils import extract_city, fetch_html, parse_float, slugify, to_soup

logger = logging.getLogger(__name__)


class SulekhaSource(Source):
    """Sulekha services directory - strong for local services and home professionals.

    Sulekha's listing markup is a Tailwind card, not the ``li.biz-listing`` /
    ``div.biz-card`` classes this adapter used to look for. The current
    structure is:

        div.w-2/3
          div.flex.items-center        -> "Verified" badge + the Sulekha Score
          div.leading-3                -> a[title] > h3  (the business name)
          address                      -> the address, with a map-pin icon

    The Score is a Sulekha quality rating **out of 10** (values like 5.6 and
    6.9), which is not comparable with a Google rating out of 5. Mapping it
    straight onto ``rating`` would silently corrupt the 0-5 scale the scorer
    uses, so it goes into ``source_score`` with its scale recorded.
    """

    name = "sulekha"
    supports_india = True
    supports_global = False

    #: Sulekha's own quality score is out of 10.
    SCORE_MAX = 10.0

    def supports(self, niche: str, area: Optional[str]) -> bool:
        return bool(niche and area)

    @staticmethod
    def _card_for(name_el):
        """Walks up from the name to the card that also holds the address."""
        node = name_el
        for _ in range(8):
            node = node.parent
            if node is None:
                return None
            if node.find("address") is not None:
                return node
        return None

    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        city = extract_city(area)
        if not city:
            return self._failed("no resolvable city in area")

        url = f"https://www.sulekha.com/{slugify(niche)}/{slugify(city)}"
        html = await fetch_html(url)
        soup = to_soup(html)
        if soup is None:
            return self._failed(f"could not fetch {url}")

        name_els = soup.select("h3")
        if not name_els:
            return self._failed(f"no listing markup at {url}")

        leads: List[RawLead] = []
        seen = set()
        for name_el in name_els:
            if len(leads) >= limit:
                break
            try:
                name = name_el.get_text(" ", strip=True)
                if not name or name.lower() in seen:
                    continue

                card = self._card_for(name_el)
                if card is None:
                    continue

                address_el = card.find("address")
                address = address_el.get_text(" ", strip=True) if address_el else None

                # The Sulekha Score: a bold orange number next to the words
                # "Sulekha Score". Out of 10, not 5.
                score = None
                score_el = card.select_one("span.font-bold.text-orange-500")
                if score_el is None:
                    for span in card.select("span"):
                        if "Sulekha Score" in span.get_text(" ", strip=True):
                            prev = span.find_previous("span")
                            score = parse_float(prev.get_text() if prev else None)
                            break
                else:
                    score = parse_float(score_el.get_text())

                verified = bool(card.select_one("svg.lucide-badge-check")) or (
                    "Verified" in card.get_text(" ", strip=True)
                )

                # The anchor's title carries "NAME in LOCALITY, CITY".
                link = name_el.find_parent("a")
                website = None
                if link is not None:
                    href = link.get("href") or ""
                    if href.startswith("http") and "sulekha.com" not in href:
                        website = href

                seen.add(name.lower())
                leads.append(
                    raw_lead(
                        name=name,
                        website=website,
                        # Sulekha renders the number behind a click-to-call
                        # button; there is no phone in the markup.
                        phone=None,
                        address=address,
                        # Deliberately NOT mapped to `rating` - see the class
                        # docstring. A 6.9/10 score is not a 6.9/5 rating.
                        rating=None,
                        reviews_count=None,
                        source_score=score,
                        source_score_max=self.SCORE_MAX,
                        source_verified=verified,
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
        if not html:
            return {"source": self.name, "available": False, "note": "could not fetch"}
        soup = to_soup(html)
        count = len(soup.select("h3")) if soup else 0
        return {
            "source": self.name,
            "available": count > 0,
            "note": None if count else "listing markup changed - no h3 cards found",
        }
