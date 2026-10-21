"""Celery tasks for distributed deployments.

Two things were broken here before:

1. ``from app.scraper.maps_scraper import scrape_google_maps`` imported a
   function that does not exist, so ``import app.workers`` raised
   ImportError and a ``USE_CELERY=true`` deployment could not boot its
   worker at all.
2. Every task created a **new event loop** and closed it again. With
   ``postgresql+asyncpg`` the pooled connections are bound to the first
   loop that used them, so the second task in the same prefork worker failed
   with an event-loop mismatch. One long-lived loop per worker process fixes
   it.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from app.workers import celery_app
from app.workers.beat_schedule import BEAT_SCHEDULE

logger = logging.getLogger(__name__)

celery_app.conf.beat_schedule = BEAT_SCHEDULE

#: One event loop per worker process, reused by every task.
_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _run(coro):
    return _get_loop().run_until_complete(coro)


@celery_app.task
def poll_replies_task() -> Dict[str, Any]:
    """Periodic IMAP sweep of every active mailbox (Celery deployment)."""
    from app.campaigns.reply_poller import poll_all_mailboxes

    return _run(poll_all_mailboxes())


@celery_app.task
def run_campaign_schedules_task() -> Dict[str, Any]:
    """Advances every ACTIVE campaign sequence.

    Without this, a multi-step sequence only advanced when a human manually
    re-clicked "Launch" - the step-delay arithmetic existed but nothing ever
    drove it. Mirrors the in-process ``_campaign_run_loop`` in app.main.
    """
    from sqlalchemy import select
    from app.database import async_session_maker
    from app.models.campaign import Campaign, CampaignStatus
    from app.campaigns.sender import execute_campaign_step

    async def _run_all() -> Dict[str, Any]:
        async with async_session_maker() as db:
            ids = (await db.execute(
                select(Campaign.id).where(Campaign.status == CampaignStatus.ACTIVE.value)
            )).scalars().all()

        sent = 0
        for campaign_id in ids:
            try:
                result = await execute_campaign_step(campaign_id)
                sent += int(result.get("sent_count") or 0)
            except Exception as exc:
                logger.warning("campaign %s tick error: %s", campaign_id, exc)
        return {"campaigns": len(ids), "sent": sent}

    return _run(_run_all())


@celery_app.task
def reset_daily_send_counters_task() -> Dict[str, Any]:
    """Resets the per-day send counters.

    ``Mailbox.sent_today`` is a *calendar day* counter. It was incremented on
    every send and reset nowhere, which quietly turned it into a lifetime
    cap - after ``daily_limit`` sends the mailbox was excluded from rotation
    forever and the outreach engine stopped after 50 emails.
    """
    from sqlalchemy import update
    from app.database import async_session_maker
    from app.models.mailbox import Mailbox

    async def _reset() -> Dict[str, Any]:
        async with async_session_maker() as db:
            result = await db.execute(
                update(Mailbox).values(sent_today=0, sent_today_date=None)
            )
            await db.commit()
            return {"reset": result.rowcount or 0}

    return _run(_reset())


@celery_app.task
def run_scrape_task(query: str, max_results: int = 20):
    """Scrapes Google Maps for a query and persists the leads."""
    from app.scraper.maps_scraper import scrape_leads_and_save
    from app.models.scrape_job import ScrapeJob
    from app.database import async_session_maker

    async def _scrape():
        async with async_session_maker() as db:
            job = ScrapeJob(query=query, status="running")
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id
        saved, new_ids = await scrape_leads_and_save(
            query=query, max_results=max_results, job_id=job_id
        )
        return {"saved": saved, "business_ids": new_ids}

    return _run(_scrape())


@celery_app.task
def enrich_and_verify_business(business_id: int, website: str):
    """Crawls one business site and SMTP-verifies every address found."""
    from app.enricher.email_finder import crawl_website_for_contacts
    from app.verifier.smtp_verifier import verify_email_async

    async def _enrich():
        crawled = await crawl_website_for_contacts(website)
        emails = crawled.get("emails", [])
        valid_emails = []
        for email in emails:
            result = await verify_email_async(email)
            if result.is_deliverable:
                valid_emails.append(email)
        return valid_emails

    return _run(_enrich())
