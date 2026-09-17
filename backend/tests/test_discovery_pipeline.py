import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.discovery.pipeline import run_discovery
from app.models.business import Business
from app.models.icp_profile import ICPProfile
from app.models.scrape_job import ScrapeJob


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

        # The duplicate lead across the two sources must only exist once.
        businesses = (await db.execute(select(Business))).scalars().all()
        names = [b.name for b in businesses]
        assert names.count("Smile Dental Clinic Delhi") == 1
        assert "Care Dental Studio" in names

        for lead in saved_job.result["ranked_leads"]:
            assert lead["score"] >= icp_profile.min_score
