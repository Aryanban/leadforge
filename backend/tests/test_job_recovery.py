"""Jobs that a restart interrupted.

A scrape or a discovery runs in-process (FastAPI BackgroundTasks) or in a
Celery worker. A restart in the middle leaves the job row at "running",
and it stays there forever because nothing is left running to finish it
or fail it. The operator sees a job that has been "running" for three
days and cannot tell whether it is stuck, finished, or lost.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker, recover_orphaned_jobs
from app.models.scrape_job import ScrapeJob


@pytest.mark.asyncio
async def test_a_job_interrupted_by_a_restart_is_failed_not_left_running():
    await recover_orphaned_jobs()

    async with async_session_maker() as db:
        db.add(ScrapeJob(query="dentists in Pune", status="running"))
        db.add(ScrapeJob(query="dentists in Delhi", status="pending"))
        await db.commit()

    recovered = await recover_orphaned_jobs()
    assert recovered == 2

    async with async_session_maker() as db:
        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        for job in jobs:
            assert job.status == "failed", f"{job.query} is still {job.status}"
            assert job.error and "restart" in job.error.lower()


@pytest.mark.asyncio
async def test_a_finished_job_is_left_alone():
    async with async_session_maker() as db:
        db.add(ScrapeJob(query="done already", status="completed"))
        await db.commit()

    recovered = await recover_orphaned_jobs()
    assert recovered == 0

    async with async_session_maker() as db:
        job = (await db.execute(select(ScrapeJob))).scalar_one()
        assert job.status == "completed"
        assert job.error is None


@pytest.mark.asyncio
async def test_recovery_is_idempotent():
    """Running it twice must not keep re-failing the same job."""
    async with async_session_maker() as db:
        db.add(ScrapeJob(query="stuck", status="running"))
        await db.commit()

    assert await recover_orphaned_jobs() == 1
    assert await recover_orphaned_jobs() == 0
