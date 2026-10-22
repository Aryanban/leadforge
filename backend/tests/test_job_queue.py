"""The job queue.

A scrape or a bulk enrichment used to run as a FastAPI ``BackgroundTask``,
which dies with the process: an API restart mid-run lost the work, and the
job row stayed at "running" forever. With Celery enabled the work goes to
a worker, and the API must not lose the job if the broker is
unreachable - it falls back to the in-process task instead of failing the
request.
"""

import pytest

from app.config import settings
from app.models.scrape_job import ScrapeJob


def _fake_celery_task(calls, fail=False):
    class _FakeTask:
        @staticmethod
        def delay(*args, **kwargs):
            if fail:
                raise RuntimeError("broker unreachable")
            calls.append((args, kwargs))
            return "task-id"

    return _FakeTask


@pytest.fixture(autouse=True)
def _no_real_scrape(monkeypatch):
    """The fallback path really runs the scrape - which takes minutes.

    The tests are about the dispatch decision, not about scraping, so the
    scrape itself is stubbed out.
    """
    import app.api.scraper as scraper_api

    async def _fake_scrape(*args, **kwargs):
        return (0, [])

    monkeypatch.setattr(scraper_api, "scrape_leads_and_save", _fake_scrape)


@pytest.mark.asyncio
async def test_a_scrape_is_dispatched_to_celery_when_it_is_enabled(monkeypatch):
    from httpx import AsyncClient
    from app.main import app

    calls = []
    monkeypatch.setattr(settings, "USE_CELERY", True, raising=False)

    import app.workers.tasks as worker_tasks

    monkeypatch.setattr(
        worker_tasks, "run_scrape_job_task", _fake_celery_task(calls), raising=False
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/scraper/start",
            json={"query": "dentists in Pune", "max_results": 5},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["dispatched"] == "celery"
        assert calls, "the job should have been handed to a worker"
        # The worker is given the job id, not a second job to create.
        assert calls[0][0][0] == body["job_id"]


@pytest.mark.asyncio
async def test_an_unreachable_broker_does_not_lose_the_job(monkeypatch):
    """A broker that is down must not fail the request and lose the work."""
    from httpx import AsyncClient
    from app.main import app

    monkeypatch.setattr(settings, "USE_CELERY", True, raising=False)

    import app.workers.tasks as worker_tasks

    monkeypatch.setattr(
        worker_tasks, "run_scrape_job_task", _fake_celery_task([], fail=True),
        raising=False,
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/scraper/start",
            json={"query": "dentists in Pune", "max_results": 5},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["dispatched"] == "background_task"

    # And the job row exists, so the operator can see it and the recovery
    # pass can fail it if the process dies.
    from app.database import async_session_maker
    from sqlalchemy import select

    async with async_session_maker() as db:
        job = (await db.execute(
            select(ScrapeJob).where(ScrapeJob.id == body["job_id"])
        )).scalar_one()
        assert job is not None
        assert job.query == "dentists in Pune"


@pytest.mark.asyncio
async def test_without_celery_the_job_runs_in_process(monkeypatch):
    from httpx import AsyncClient
    from app.main import app

    monkeypatch.setattr(settings, "USE_CELERY", False, raising=False)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/scraper/start",
            json={"query": "dentists in Nagpur", "max_results": 3},
        )
        assert res.status_code == 200
        assert res.json()["dispatched"] == "background_task"


@pytest.mark.asyncio
async def test_bulk_enrichment_also_goes_to_the_queue(monkeypatch):
    from httpx import AsyncClient
    from app.main import app

    calls = []
    monkeypatch.setattr(settings, "USE_CELERY", True, raising=False)

    import app.workers.tasks as worker_tasks

    monkeypatch.setattr(
        worker_tasks, "enrich_all_pending_task", _fake_celery_task(calls),
        raising=False,
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post("/api/v1/enricher/enrich-all?limit=5")
        assert res.status_code == 200
        assert res.json()["dispatched"] == "celery"
        assert calls
