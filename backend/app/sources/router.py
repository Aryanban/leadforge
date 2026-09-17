import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.database import async_session_maker
from app.models.source_stats import SourceStats

from .base import Source
from .google_maps import GoogleMapsSource
from .indiamart import IndiaMARTSource
from .justdial import JustDialSource
from .sulekha import SulekhaSource

logger = logging.getLogger(__name__)

REGISTRY: List[Source] = [
    GoogleMapsSource(),
    JustDialSource(),
    IndiaMARTSource(),
    SulekhaSource(),
]

BY_NAME: Dict[str, Source] = {source.name: source for source in REGISTRY}


async def _learned_priority(niche: str, area: Optional[str]) -> Dict[str, float]:
    """Higher score = historically better yield for this niche+area (or niche alone)."""
    scored: Dict[str, float] = {}
    try:
        async with async_session_maker() as db:
            stmt = select(SourceStats).where(
                (SourceStats.niche == (niche or "").title())
                | (SourceStats.niche == "")
            )
            res = await db.execute(stmt)
            for stats in res.scalars().all():
                priority = (stats.avg_score or 0.0) * min(1.0, (stats.leads_found or 0) / 10.0)
                # Prefer stats that match this exact area, then niche-wide stats.
                if stats.area and area and stats.area.lower() in area.lower():
                    priority += 15
                scored[stats.source] = max(scored.get(stats.source or "", 0.0), priority)
    except Exception as e:
        logger.debug(f"learned priority lookup failed: {e}")
    return scored


async def select_sources(
    niche: str,
    area: Optional[str],
    icp_profile: Any = None,
) -> List[Source]:
    """
    Chooses and orders the sources for a discovery run.

    Manual preferred_sources always win; otherwise the learned SourceStats
    ranking decides — that's the "it knows where to find them" behaviour.
    """
    eligible = [s for s in REGISTRY if s.supports(niche, area)]
    if not eligible:
        return []

    preferred: List[str] = []
    if icp_profile is not None:
        preferred = list(getattr(icp_profile, "preferred_sources", None) or [])

    learned = await _learned_priority(niche, area)

    def priority_key(source: Source) -> float:
        if source.name in preferred:
            return 1000.0 - preferred.index(source.name)
        return learned.get(source.name, 50.0 if source.name == "google_maps" else 0.0)

    return sorted(eligible, key=priority_key, reverse=True)


async def discover(
    niche: str,
    area: Optional[str],
    limit: int = 20,
    icp_profile: Any = None,
    sources: Optional[List[str]] = None,
) -> Dict[str, List[dict]]:
    """Runs every selected source and returns leads grouped by source name."""
    if sources:
        chosen: List[Source] = [
            BY_NAME[name] for name in sources if name in BY_NAME and BY_NAME[name].supports(niche, area)
        ]
    else:
        chosen = await select_sources(niche, area, icp_profile)

    results: Dict[str, List[dict]] = {}
    for source in chosen:
        try:
            leads = await source.search(niche, area, limit=limit)
            results[source.name] = leads or []
            logger.info(f"[{source.name}] returned {len(results[source.name])} raw leads")
        except Exception as e:
            logger.warning(f"[{source.name}] failed during discovery: {e}")
            results[source.name] = []
    return results


def list_available_sources() -> List[Dict[str, Any]]:
    return [
        {
            "name": source.name,
            "supports_india": source.supports_india,
            "supports_global": source.supports_global,
        }
        for source in REGISTRY
    ]
