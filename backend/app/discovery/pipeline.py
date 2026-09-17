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
    ranked: List[Dict[str, Any]],
) -> None:
    """Persists per-source yield quality so the router can learn over time."""
    from app.models.source_stats import SourceStats

    if not ranked:
        return
    try:
        async with async_session_maker() as db:
            stmt = select(SourceStats).where(
                SourceStats.source == source,
                SourceStats.niche == (niche or ""),
                SourceStats.area == (area or ""),
            )
            res = await db.execute(stmt)
            stats = res.scalars().first()

            avg = sum(lead["score"] for lead in ranked) / len(ranked)
            hot = sum(1 for lead in ranked if lead["tier"] == "HOT")

            if stats is None:
                stats = SourceStats(
                    source=source,
                    niche=niche or "",
                    area=area or "",
                    leads_found=len(ranked),
                    enriched=len(ranked),
                    avg_score=avg,
                    hot_leads=hot,
                )
                db.add(stats)
            else:
                stats.leads_found += len(ranked)
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

    1. Scrape sources for the niche+area (P0: Google Maps incl. HTTP fallback).
    2. Enrich new leads (emails, phones, socials, SMTP verification, health probes).
    3. Rank every lead against the ICP and keep those above the min-score gate.
    4. Persist the ranked shortlist on the ScrapeJob for the dashboard to render.
    """
    from app.scraper.maps_scraper import scrape_leads_and_save

    async with async_session_maker() as db:
        job = await db.get(ScrapeJob, job_id)
        icp_profile = await db.get(ICPProfile, icp_profile_id)
        if job is None or icp_profile is None:
            raise ValueError("Discovery job or ICP profile not found")

        job.status = "running"
        await db.commit()

    query = f"{niche} in {area}".strip() if area else niche.strip()

    try:
        saved_count, new_biz_ids = await scrape_leads_and_save(
            job_id, query, max_results,
            icp_profile_id=icp_profile_id,
            enrich=False,
        )
    except Exception as e:
        async with async_session_maker() as db:
            job = await db.get(ScrapeJob, job_id)
            job.status = "failed"
            job.error = f"Scraping failed: {e}"
            await db.commit()
        raise

    await _enrich_new_leads(new_biz_ids)

    ranked: List[Dict[str, Any]] = []
    try:
        async with async_session_maker() as db:
            stmt = (
                select(Business)
                .options(selectinload(Business.contacts))
                .where(Business.id.in_(new_biz_ids))
            )
            res = await db.execute(stmt)
            businesses = list(res.scalars().all())

            contacts_by_business: Dict[int, List[Contact]] = {
                business.id: list(business.contacts) for business in businesses
            }

            ranked = rank_businesses(businesses, contacts_by_business, icp_profile, limit=max_results)
    except Exception as e:
        logger.warning(f"Ranking failed for job {job_id}: {e}")

    primary_source = (sources[0] if sources else "google_maps") or "google_maps"
    await _record_source_stats(primary_source, niche, area, ranked)

    async with async_session_maker() as db:
        job = await db.get(ScrapeJob, job_id)
        job.status = "completed"
        job.total_found = saved_count
        job.leads_saved = len(ranked)
        job.result = {
            "niche": niche,
            "area": area,
            "query": query,
            "icp_profile_id": icp_profile_id,
            "min_score": icp_profile.min_score,
            "preset": icp_profile.preset,
            "ranked_leads": ranked,
        }
        job.finished_at = datetime.utcnow()
        await db.commit()

    logger.info(
        f"Discovery job {job_id} completed: {saved_count} scraped, {len(ranked)} passed "
        f"the ICP gate (min_score={icp_profile.min_score})"
    )
    return {"job_id": job_id, "scraped": saved_count, "ranked_leads": ranked}
