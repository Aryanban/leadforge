import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class RawLead(TypedDict, total=False):
    """Normalised lead shape every source adapter must emit."""
    name: str
    website: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    reviews_count: Optional[int]
    industry: Optional[str]
    place_id: Optional[str]
    maps_url: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    is_claimed: bool
    operational_status: Optional[str]
    price_tier: Optional[str]
    source: str
    query: str
    #: A source-specific quality score on its own scale. Sulekha rates out of
    #: 10, Google out of 5 - folding them into one `rating` field would
    #: silently corrupt the 0-5 scale the scorer uses.
    source_score: Optional[float]
    source_score_max: Optional[float]
    #: Whether the directory verified the listing itself.
    source_verified: Optional[bool]


class SourceHealth(TypedDict):
    source: str
    available: bool
    note: Optional[str]


class Source(ABC):
    """Pluggable lead source. Adapters discover businesses for a niche+area."""

    name: str = "base"
    supports_india: bool = False
    supports_global: bool = False

    #: Set by :meth:`_failed` so ``health()`` can explain an empty result.
    #: A source that silently returns [] is indistinguishable from a niche
    #: with no businesses, which is how a broken adapter hides for months.
    _last_note: Optional[str] = None

    @abstractmethod
    def supports(self, niche: str, area: Optional[str]) -> bool:
        """Whether this source can serve the given niche/location."""

    @abstractmethod
    async def search(self, niche: str, area: Optional[str], limit: int = 20) -> List[RawLead]:
        """Return raw leads for the niche+area. Failures must return []."""

    async def health(self) -> SourceHealth:
        return {
            "source": self.name,
            "available": self._last_note is None,
            "note": self._last_note,
        }

    def build_query(self, niche: str, area: Optional[str]) -> str:
        return f"{niche} in {area}".strip() if area else niche.strip()

    def _failed(self, message: str) -> List[RawLead]:
        logger.warning(f"Source '{self.name}' failed: {message}")
        self._last_note = message
        return []


def raw_lead(**fields: Any) -> RawLead:
    base: Dict[str, Any] = {
        "website": None,
        "phone": None,
        "address": None,
        "rating": None,
        "reviews_count": None,
        "industry": None,
        "place_id": None,
        "maps_url": None,
        "latitude": None,
        "longitude": None,
        "is_claimed": True,
        "operational_status": None,
        "price_tier": None,
        "source_score": None,
        "source_score_max": None,
        "source_verified": None,
    }
    base.update(fields)
    return RawLead(base)  # type: ignore[arg-type]
