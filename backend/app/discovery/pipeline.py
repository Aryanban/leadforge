import asyncio
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

#: How many leads to enrich at once. Each enrichment is a multi-request
#: waterfall (search engines, a website crawl, an SMTP verification), so it
#: is almost entirely I/O bound - concurrency is close to free.
ENRICH_CONCURRENCY = 8


async def _enrich_new_leads(business_ids: List[int],
                            concurrency: int = ENRICH_CONCURRENCY) -> int:
    """ICP-aware enrichment for freshly discovered leads (best-effort).

    Enrichment used to run strictly one lead at a time. Measured at ~9s per
    lead, so a 100-lead discovery job spent roughly 15 minutes - inside the
    FastAPI event loop, with no other request served. Running the leads
    concurrently (each one is I/O bound) brings that to ~2 minutes.

    Failures are isolated: one lead that raises must not cancel the others.
    """
    from app.enricher.email_finder import enrich_business_by_id

    if not business_ids:
        return 0

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(business_id: int) -> int:
        async with semaphore:
            try:
                await enrich_business_by_id(business_id)
                return 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Enrichment failed for business {business_id}: {e}")
                return 0

    results = await asyncio.gather(*(_one(bid) for bid in business_ids))
    return sum(results)


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
                    score_samples=len(ranked),
                    hot_leads=hot,
                )
                db.add(stats)
            else:
                previous_enriched = stats.enriched or 0
                new_enriched = len(ranked)
                previous_samples = stats.score_samples or 0
                stats.leads_found += discovered
                stats.enriched = previous_enriched + new_enriched
                if new_enriched:
                    if previous_samples:
                        stats.avg_score = (
                            (stats.avg_score or 0.0) * previous_samples + avg * new_enriched
                        ) / (previous_samples + new_enriched)
                    else:
                        # Discard the old blended average, which predates
                        # correct per-source attribution.
                        stats.avg_score = avg
                    stats.score_samples = previous_samples + new_enriched
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
    per_source_ids: Dict[str, List[int]] = {}
    async with async_session_maker() as db:
        for source_name, raw_leads in raw_by_source.items():
            try:
                new_ids = await _persist(db, raw_leads, icp_profile_id, job_id, query)
            except Exception as e:
                logger.warning(f"Persistence failed for source '{source_name}': {e}")
                new_ids = []
            per_source_counts[source_name] = len(raw_leads)
            per_source_ids[source_name] = new_ids
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
            from app.qualifier.source_trust import source_trust_overrides

            trust_overrides = await source_trust_overrides(db)

            ranked_by_source: Dict[str, List[Dict[str, Any]]] = {}
            for source_name, business_ids in per_source_ids.items():
                source_id_set = set(business_ids)
                source_businesses = [b for b in businesses if b.id in source_id_set]
                ranked_by_source[source_name] = rank_businesses(
                    source_businesses,
                    contacts_by_business,
                    icp_profile,
                    limit=max_results,
                    source_trust_by_source=trust_overrides,
                )
            ranked = sorted(
                (lead for leads in ranked_by_source.values() for lead in leads),
                key=lambda lead: lead["score"],
                reverse=True,
            )[:max_results]
    except Exception as e:
        logger.warning(f"Ranking failed for job {job_id}: {e}")
        ranked_by_source = {source_name: [] for source_name in per_source_counts}

    for source_name, count in per_source_counts.items():
        await _record_source_stats(
            source_name, niche, area, count, ranked_by_source.get(source_name, [])
        )

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
