from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import List, Optional

import logging

from app.config import settings
from app.database import get_db
from app.models.scrape_job import ScrapeJob
from app.scraper.maps_scraper import scrape_leads_and_save

logger = logging.getLogger(__name__)

router = APIRouter()

class ScrapeRequest(BaseModel):
    query: str = Field(..., min_length=2, example="Real Estate Agents in Rohini Delhi")
    max_results: int = Field(20, ge=1, le=100)

@router.post("/start")
async def start_scraping(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    # 1. Create ScrapeJob record in DB
    job = ScrapeJob(
        query=request.query.strip(),
        status="pending",
        total_found=0,
        leads_saved=0
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 2. Dispatch the work.
    #
    # With Celery enabled the job goes to a worker, so it survives an API
    # restart and can be retried. Without it the work runs as a FastAPI
    # background task - which dies with the process, and a job left at
    # "running" is recovered and failed on the next boot.
    dispatched = "background_task"
    if getattr(settings, "USE_CELERY", False):
        try:
            from app.workers.tasks import run_scrape_job_task

            run_scrape_job_task.delay(job.id)
            dispatched = "celery"
        except Exception as exc:
            # A broker that is not reachable must not lose the job: fall
            # back to the in-process task rather than failing the request.
            logger.warning(
                "Celery dispatch failed (%s); running the scrape in-process", exc
            )

    if dispatched == "background_task":
        background_tasks.add_task(
            scrape_leads_and_save, job.id, request.query.strip(), request.max_results
        )

    return {
        "job_id": job.id,
        "query": job.query,
        "status": "started",
        "dispatched": dispatched,
        "message": f"Scrape job queued for '{job.query}'"
    }


@router.get("/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    stmt = select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(20)
    res = await db.execute(stmt)
    jobs = res.scalars().all()
    return [
        {
            "id": j.id,
            "query": j.query,
            "status": j.status,
            "total_found": j.total_found,
            "leads_saved": j.leads_saved,
            "error": j.error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "query": job.query,
        "status": job.status,
        "total_found": job.total_found,
        "leads_saved": job.leads_saved,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None
    }
