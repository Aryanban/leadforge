import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.discovery.pipeline import _record_source_stats, run_discovery
from app.models.business import Business
from app.models.icp_profile import ICPProfile
from app.models.scrape_job import ScrapeJob
from app.models.source_stats import SourceStats


@pytest.fixture
async def icp_profile(db_session):
    profile = ICPProfile(
        name="Pipeline Test ICP",
        niche="Dentist",
        area="Delhi",
        keywords=["dental", "dentist"],
        min_score=20,
        preset="outreach_quality",
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.fixture
def stub_sources(monkeypatch):
    """Two fake sources, one returning a lead that already exists (dedupe check)."""

    async def fake_run_sources(niche, area, limit, icp_profile, sources):
        return {
            "fake_source": [
                {"name": "Smile Dental Clinic Delhi", "phone": "+91 98765 43210", "industry": "Dentist",
                 "source": "fake_source"},
                {"name": "Care Dental Studio", "phone": "+91 98765 54321", "industry": "Dentist",
                 "source": "fake_source"},
            ],
            "second_source": [
                {"name": "Smile Dental Clinic Delhi", "phone": "+91 98765 43210", "industry": "Dentist",
                 "source": "second_source"},
            ],
        }

    async def fake_enrich(business_ids):
        return len(business_ids)

    monkeypatch.setattr("app.discovery.pipeline.run_sources", fake_run_sources)
    monkeypatch.setattr("app.discovery.pipeline._enrich_new_leads", fake_enrich)


@pytest.mark.asyncio
async def test_run_discovery_dedupes_and_ranks(db_session, icp_profile, stub_sources):
    job = ScrapeJob(query="Dentist in Delhi", status="pending")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    result = await run_discovery(
        job_id=job.id,
        niche="Dentist",
        area="Delhi",
        icp_profile_id=icp_profile.id,
        max_results=10,
    )

    assert result["scraped"] == 3  # 2 + 1 raw leads across sources

    async with async_session_maker() as db:
        saved_job = await db.get(ScrapeJob, job.id)
        assert saved_job.status == "completed"
        assert saved_job.icp_profile_id == icp_profile.id
        assert sorted(saved_job.result["sources_used"]) == ["fake_source", "second_source"]
        assert saved_job.result["per_source_counts"]["fake_source"] == 2
        assert saved_job.result["per_source_counts"]["second_source"] == 1

        # Source performance is measured against businesses that source
        # actually contributed after deduplication. The duplicate returned by
        # second_source must not inherit fake_source's ranked scores.
        stats = (await db.execute(select(SourceStats))).scalars().all()
        stats_by_source = {row.source: row for row in stats}
        assert stats_by_source["fake_source"].enriched > 0
        assert stats_by_source["fake_source"].avg_score > 0
        assert stats_by_source["second_source"].enriched == 0
        assert stats_by_source["second_source"].avg_score == 0

        # The duplicate lead across the two sources must only exist once.
        businesses = (await db.execute(select(Business))).scalars().all()
        names = [b.name for b in businesses]
        assert names.count("Smile Dental Clinic Delhi") == 1
        assert "Care Dental Studio" in names

        for lead in saved_job.result["ranked_leads"]:
            assert lead["score"] >= icp_profile.min_score


@pytest.mark.asyncio
async def test_source_stats_replace_legacy_average_then_weight_new_observations(db_session):
    legacy = SourceStats(
        source="example_source",
        niche="Dentist",
        area="Delhi",
        leads_found=100,
        enriched=100,
        avg_score=90.0,
        score_samples=0,
    )
    db_session.add(legacy)
    await db_session.commit()

    await _record_source_stats(
        "example_source", "Dentist", "Delhi", 5,
        [{"score": 40, "tier": "WARM"}],
    )
    await _record_source_stats(
        "example_source", "Dentist", "Delhi", 5,
        [{"score": 60, "tier": "HOT"}],
    )

    async with async_session_maker() as db:
        stats = (await db.execute(select(SourceStats))).scalars().one()
        assert stats.avg_score == 50.0
        assert stats.score_samples == 2
        assert stats.enriched == 102
