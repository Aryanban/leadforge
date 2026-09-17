import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.icp_profile import ICPProfile
from app.models.scrape_job import ScrapeJob
from app.qualifier.ranker import rank_businesses
from app.sources.router import discover as run_sources

logger = logging.getLogger(__name__)


async def _enrich_new_leads(business_ids: List[int]) -> int:
    """ICP-aware enrichment for freshly discovered leads (best-effort)."""
    from app.enricher.email_finder import enrich_business_by_id

    enriched = 0
    for business_id in business_ids:
        try:
            await enrich_business_by_id(business_id)
            enriched += 1
        except Exception as e:
            logger.warning(f"Enrichment failed for business {business_id}: {e}")
    return enriched


async def _record_source_stats(
    source: str,
    niche: Optional[str],
    area: Optional[str],
    discovered: int,
    ranked: List[Dict[str, Any]],
) -> None:
    """Persists per-source yield quality so the router learns over time."""
    from app.models.source_stats import SourceStats

    if discovered == 0 and not ranked:
        return
    try:
        async with async_session_maker() as db:
            stmt = select(SourceStats).where(
                SourceStats.source == source,
                SourceStats.niche == (niche or "").title(),
                SourceStats.area == (area or ""),
            )
            res = await db.execute(stmt)
            stats = res.scalars().first()

            avg = (sum(lead["score"] for lead in ranked) / len(ranked)) if ranked else 0.0
            hot = sum(1 for lead in ranked if lead["tier"] == "HOT")

            if stats is None:
                stats = SourceStats(
                    source=source,
                    niche=(niche or "").title(),
                    area=area or "",
                    leads_found=discovered,
                    enriched=len(ranked),
                    avg_score=avg,
                    hot_leads=hot,
                )
                db.add(stats)
            else:
                stats.leads_found += discovered
                stats.enriched += len(ranked)
                stats.avg_score = (stats.avg_score or 0) * 0.7 + avg * 0.3
                stats.hot_leads += hot
            await db.commit()
    except Exception as e:
        logger.warning(f"Source stats update failed for '{source}': {e}")


async def run_discovery(
    job_id: int,
    niche: str,
    area: Optional[str],
    icp_profile_id: int,
    max_results: int = 20,
    sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Full discovery pipeline for an ICP profile:

    1. Route the niche+area to the best sources (learned over time).
    2. Discover raw leads from every source, dedupe against known businesses.
    3. Enrich the new leads (emails, phones, socials, SMTP verification, health probes).
    4. Rank every lead against the ICP and keep those above the min-score gate.
    5. Persist the ranked shortlist on the ScrapeJob for the dashboard to render.
    """
    async with async_session_maker() as db:
        job = await db.get(ScrapeJob, job_id)
        icp_profile = await db.get(ICPProfile, icp_profile_id)
        if job is None or icp_profile is None:
            raise ValueError("Discovery job or ICP profile not found")

        job.status = "running"
        job.icp_profile_id = icp_profile_id
        await db.commit()

    query = f"{niche} in {area}".strip() if area else niche.strip()

    raw_by_source: Dict[str, List[dict]] = {}
    try:
        raw_by_source = await run_sources(niche, area, max_results, icp_profile, sources)
    except Exception as e:
        async with async_session_maker() as db:
            job = await db.get(ScrapeJob, job_id)
            job.status = "failed"
            job.error = f"Source routing failed: {e}"
            await db.commit()
        raise

    all_new_ids: List[int] = []
    per_source_counts: Dict[str, int] = {}
    async with async_session_maker() as db:
        for source_name, raw_leads in raw_by_source.items():
            try:
                new_ids = await _persist(db, raw_leads, icp_profile_id, job_id, query)
            except Exception as e:
                logger.warning(f"Persistence failed for source '{source_name}': {e}")
                new_ids = []
            per_source_counts[source_name] = len(raw_leads)
            all_new_ids.extend(new_ids)

    await _enrich_new_leads(all_new_ids)

    ranked: List[Dict[str, Any]] = []
    try:
        async with async_session_maker() as db:
            stmt = (
                select(Business)
                .options(
                    selectinload(Business.contacts),
                    selectinload(Business.social_profiles),
                )
                .where(Business.id.in_(all_new_ids))
            )
            res = await db.execute(stmt)
            businesses = list(res.scalars().all())

            contacts_by_business: Dict[int, List[Contact]] = {
                business.id: list(business.contacts) for business in businesses
            }

            ranked = rank_businesses(businesses, contacts_by_business, icp_profile, limit=max_results)
    except Exception as e:
        logger.warning(f"Ranking failed for job {job_id}: {e}")

    for source_name, count in per_source_counts.items():
        await _record_source_stats(source_name, niche, area, count, ranked)

    async with async_session_maker() as db:
        job = await db.get(ScrapeJob, job_id)
        job.status = "completed"
        job.total_found = sum(per_source_counts.values())
        job.leads_saved = len(ranked)
        job.result = {
            "niche": niche,
            "area": area,
            "query": query,
            "icp_profile_id": icp_profile_id,
            "min_score": icp_profile.min_score,
            "preset": icp_profile.preset,
            "sources_used": list(raw_by_source.keys()),
            "per_source_counts": per_source_counts,
            "ranked_leads": ranked,
        }
        job.finished_at = datetime.utcnow()
        await db.commit()

    logger.info(
        f"Discovery job {job_id} completed: {job.total_found} scraped across "
        f"{len(per_source_counts)} sources, {len(ranked)} passed the ICP gate "
        f"(min_score={icp_profile.min_score})"
    )
    return {"job_id": job_id, "scraped": job.total_found, "ranked_leads": ranked}


async def _persist(
    db: AsyncSession,
    raw_leads: List[dict],
    icp_profile_id: Optional[int],
    job_id: Optional[int],
    query: str,
) -> List[int]:
    """Dedupe-aware persistence for one source's raw leads."""
    from app.dedupe.persist import persist_raw_leads

    for lead in raw_leads:
        lead.setdefault("query", query)
    return await persist_raw_leads(db, raw_leads, icp_profile_id, job_id=job_id)
