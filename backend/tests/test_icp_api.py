import pytest
from starlette.testclient import TestClient

from app.api import icp as icp_api
from app.main import app
from app.models.business import Business
from app.models.contact import Contact
from app.models.icp_profile import ICPProfile

client = TestClient(app)


@pytest.fixture
def profile_id() -> int:
    response = client.post(
        "/api/v1/icp",
        json={
            "name": "Rohini Realty Test ICP",
            "niche": "Real Estate Agency",
            "area": "Rohini Delhi",
            "keywords": ["realty"],
            "exclude_keywords": ["shutter"],
            "min_score": 30,
            "preset": "outreach_quality",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_and_list_icp_profile(profile_id):
    assert profile_id > 0

    response = client.get("/api/v1/icp")
    assert response.status_code == 200
    profiles = response.json()
    assert any(p["id"] == profile_id for p in profiles)

    detail = client.get(f"/api/v1/icp/{profile_id}")
    assert detail.status_code == 200
    assert detail.json()["niche"] == "Real Estate Agency"


@pytest.mark.asyncio
async def test_update_and_delete_icp_profile(profile_id):
    response = client.put(f"/api/v1/icp/{profile_id}", json={"min_score": 65, "preset": "agency_opportunity"})
    assert response.status_code == 200
    assert response.json()["min_score"] == 65
    assert response.json()["preset"] == "agency_opportunity"

    response = client.put(f"/api/v1/icp/{profile_id}", json={"preset": "bogus"})
    assert response.status_code == 422

    response = client.delete(f"/api/v1/icp/{profile_id}")
    assert response.status_code == 200
    assert client.get(f"/api/v1/icp/{profile_id}").status_code == 404


def test_parse_endpoint_drafts_icp():
    response = client.post("/api/v1/icp/parse", json={"text": "Dentists in South Delhi with verified emails"})
    assert response.status_code == 200
    drafted = response.json()
    assert drafted["area"] == "South Delhi"
    assert drafted["min_score"] == 60
    assert drafted["niche"].lower().startswith("dentist")


@pytest.mark.asyncio
async def test_rank_returns_scored_leads(db_session, profile_id):
    business = Business(
        name="Metro Prime Realty Associates",
        phone="+91 98101 99887",
        website="https://metroprimerealty.example.in",
        address="Main Road, Sector 25, Rohini, Delhi",
        rating=4.8,
        reviews_count=63,
        industry="Real Estate Agency",
        source="test",
        icp_profile_id=profile_id,
        extra_data={"is_claimed": True},
    )
    db_session.add(business)
    await db_session.flush()

    contact = Contact(
        business_id=business.id,
        first_name="Amit",
        last_name="Verma",
        title="Partner",
        email="amit@metroprimerealty.example.in",
        phone="+91 98101 99887",
        whatsapp_link="https://wa.me/919810199887",
        is_verified=True,
        verification_status="valid",
        source="test",
    )
    db_session.add(contact)
    await db_session.commit()

    response = client.post(f"/api/v1/icp/{profile_id}/rank?limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["icp_profile_id"] == profile_id
    assert payload["total"] >= 1

    lead = next(l for l in payload["ranked_leads"] if l["name"] == "Metro Prime Realty Associates")
    assert lead["score"] >= 30
    assert lead["tier"] in ("HOT", "WARM", "COLD")
    assert lead["signal_breakdown"]["verified_email"] > 0
    assert lead["contacts"][0]["email"] == "amit@metroprimerealty.example.in"


@pytest.mark.asyncio
async def test_discovery_job_runs_and_stores_result(monkeypatch, db_session, profile_id):
    """The discover endpoint should queue and persist ranked results end-to-end."""
    async def fake_pipeline(job_id, niche, area, icp_profile_id, max_results, sources):
        from app.database import async_session_maker
        from app.models.scrape_job import ScrapeJob
        from datetime import datetime

        async with async_session_maker() as db:
            job = await db.get(ScrapeJob, job_id)
            assert job is not None
            job.status = "completed"
            job.total_found = 1
            job.leads_saved = 1
            job.result = {"niche": niche, "area": area, "ranked_leads": [{"business_id": 1, "score": 80}]}
            job.finished_at = datetime.utcnow()
            await db.commit()
        return {"job_id": job_id, "ranked_leads": []}

    monkeypatch.setattr(icp_api, "run_discovery", fake_pipeline)

    response = client.post(
        "/api/v1/icp/discover",
        json={"niche": "Real Estate Agency", "area": "Rohini Delhi", "icp_profile_id": profile_id, "max_results": 5},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    # BackgroundTasks run synchronously inside TestClient's context; assert the result landed
    result = client.get(f"/api/v1/icp/discover/{job_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert body["result"]["area"] == "Rohini Delhi"
    assert body["result"]["ranked_leads"][0]["score"] == 80


def test_discovery_rejects_missing_profile():
    response = client.post(
        "/api/v1/icp/discover",
        json={"niche": "Dentists", "area": "Delhi", "icp_profile_id": 999999, "max_results": 5},
    )
    assert response.status_code == 404


def test_missing_icp_returns_404():
    assert client.get("/api/v1/icp/999999").status_code == 404
