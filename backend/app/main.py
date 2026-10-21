from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import asyncio
import contextlib
import logging

from app.config import settings
from typing import Optional, Any, Dict, List
from app.api import scraper, leads, enricher, campaigns, analytics, mailboxes, icp, inbox, lists, suppression, setup
from app.campaigns import tracker
from app.database import Base, engine, async_session_maker, ensure_schema
from app.seeds import seed_initial_data_if_empty
from app.auth import require_api_key, auth_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadforge")

#: How often the in-process reply poller sweeps IMAP (single-process
#: self-host default). Users on Celery get the same cadence via beat — see
#: app/workers/beat_schedule.py — and this loop disables itself when
#: USE_CELERY is true so sends are never double-counted.
REPLY_POLL_INTERVAL_SECONDS = 300

#: How often the in-process scheduler advances active campaign sequences.
#: Without this, a multi-step sequence only ever advanced when a human
#: manually re-clicked "Launch" — the step delay arithmetic existed but
#: nothing ever drove it, so the README's headline sequence feature was
#: manual-only.
CAMPAIGN_TICK_SECONDS = 300


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing LeadForge database schemas...")
    await ensure_schema()

    # Auto-seed initial realistic demo data if database is fresh
    try:
        await seed_initial_data_if_empty()
    except Exception as e:
        logger.warning(f"Seed initialization notice: {e}")

    if auth_enabled():
        logger.info("API authentication is ENABLED (API_KEY set).")

    background: list[asyncio.Task] = []
    if not settings.USE_CELERY:
        background.append(asyncio.ensure_future(_reply_poll_loop()))
        background.append(asyncio.ensure_future(_campaign_run_loop()))

    yield

    for task in background:
        task.cancel()
    for task in background:
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: B014 - shutdown is best-effort
            pass
    logger.info("LeadForge shutting down.")


async def _reply_poll_loop() -> None:
    """In-process IMAP sweep every REPLY_POLL_INTERVAL_SECONDS.

    Active only when NOT on Celery (Celery deployments use beat instead).
    One sweep failing never kills the loop — every error is logged and the
    next sweep proceeds on schedule.
    """
    from app.campaigns.reply_poller import poll_all_mailboxes

    await asyncio.sleep(60)  # let boot finish before the first sweep
    while True:
        try:
            result = await poll_all_mailboxes()
            if result.get("replies"):
                logger.info("reply poll: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - network edge cases
            logger.warning("reply poll loop error: %s", exc)
        await asyncio.sleep(REPLY_POLL_INTERVAL_SECONDS)


async def _campaign_run_loop() -> None:
    """Advances every ACTIVE campaign sequence on a fixed cadence.

    A multi-step sequence is a time-based machine: step 2 is due N days after
    step 1 was delivered. The delay arithmetic existed in
    ``campaigns.sender`` but nothing ever called it again, so the operator had
    to manually re-launch every sequence at roughly the right moment - forever.

    This loop is the thing that makes a sequence a sequence. It is deliberately
    conservative: one campaign failing never stops the others, and a campaign
    that is merely waiting on a step delay stays ACTIVE (see
    ``execute_campaign_step``) rather than being marked complete.
    """
    from sqlalchemy import select
    from app.models.campaign import Campaign, CampaignStatus
    from app.campaigns.sender import execute_campaign_step

    await asyncio.sleep(90)  # let boot finish before the first tick
    while True:
        try:
            async with async_session_maker() as db:
                campaign_ids = (await db.execute(
                    select(Campaign.id).where(
                        Campaign.status == CampaignStatus.ACTIVE.value)
                )).scalars().all()
            for campaign_id in campaign_ids:
                try:
                    result = await execute_campaign_step(campaign_id)
                    if result.get("sent_count"):
                        logger.info(
                            "campaign %s: sent %s", campaign_id, result.get("sent_count"))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("campaign %s tick error: %s", campaign_id, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("campaign loop error: %s", exc)
        await asyncio.sleep(CAMPAIGN_TICK_SECONDS)


async def _reap_stuck_sends() -> int:
    """Marks abandoned in-flight sends as failed.

    A send row is committed as "sending" *before* the SMTP call so a crash
    cannot produce a delivered email with no record. If the process dies
    mid-flight the row stays "sending" forever; this sweeps those up so the
    next run can retry them against the normal retry budget.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, update
    from app.models.send import Send

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    async with async_session_maker() as db:
        result = await db.execute(
            update(Send)
            .where(Send.status == "sending")
            .values(status="failed", error_message="interrupted before completion")
        )
        await db.commit()
        return result.rowcount or 0

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous lead generation, contact enrichment, and cold email outreach engine.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS middleware for Next.js dashboard. Origins come from CORS_ORIGINS so a
# production deployment names its dashboard explicitly instead of trusting
# every website on the internet with the user's session.
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
#: ``allow_credentials=True`` alongside a wildcard origin makes Starlette echo
#: the *attacker's* origin back on the preflight response, which turns
#: "allow all origins" into "allow any website to drive this API with the
#: user's session". Credentials are only allowed for an explicit origin list.
_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

#: Every router except the mail-facing tracker requires the API key when one
#: is configured. The tracker serves the RFC 8058 one-click unsubscribe and
#: the open-tracking pixel, which are fetched by the recipient's mail client.
_auth_dependency = [Depends(require_api_key)]

# Versioned API routes (/api/v1/...)
app.include_router(analytics.router, prefix=f"{settings.API_V1_STR}/analytics", tags=["Analytics"], dependencies=_auth_dependency)
app.include_router(scraper.router, prefix=f"{settings.API_V1_STR}/scraper", tags=["Scraper"], dependencies=_auth_dependency)
app.include_router(leads.router, prefix=f"{settings.API_V1_STR}/leads", tags=["Leads"], dependencies=_auth_dependency)
app.include_router(enricher.router, prefix=f"{settings.API_V1_STR}/enricher", tags=["Enrichment"], dependencies=_auth_dependency)
app.include_router(campaigns.router, prefix=f"{settings.API_V1_STR}/campaigns", tags=["Campaigns"], dependencies=_auth_dependency)
app.include_router(tracker.router, prefix=f"{settings.API_V1_STR}/campaigns/tracker", tags=["Campaign Tracker"])
app.include_router(mailboxes.router, prefix=f"{settings.API_V1_STR}/mailboxes", tags=["Mailboxes"], dependencies=_auth_dependency)
app.include_router(icp.router, prefix=f"{settings.API_V1_STR}/icp", tags=["ICP & Discovery"], dependencies=_auth_dependency)
app.include_router(inbox.router, prefix=f"{settings.API_V1_STR}/inbox", tags=["Inbox"], dependencies=_auth_dependency)
app.include_router(lists.router, prefix=f"{settings.API_V1_STR}/lists", tags=["Saved Lists"], dependencies=_auth_dependency)
app.include_router(suppression.router, prefix=f"{settings.API_V1_STR}/suppression", tags=["Suppression"], dependencies=_auth_dependency)
app.include_router(setup.router, prefix=f"{settings.API_V1_STR}/setup", tags=["Setup"], dependencies=_auth_dependency)

# Aliases without /v1 for backwards compatibility (/api/...)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics Legacy"], dependencies=_auth_dependency)
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper Legacy"], dependencies=_auth_dependency)
app.include_router(leads.router, prefix="/api/leads", tags=["Leads Legacy"], dependencies=_auth_dependency)
app.include_router(enricher.router, prefix="/api/enricher", tags=["Enrichment Legacy"], dependencies=_auth_dependency)
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns Legacy"], dependencies=_auth_dependency)
app.include_router(mailboxes.router, prefix="/api/mailboxes", tags=["Mailboxes Legacy"], dependencies=_auth_dependency)
app.include_router(icp.router, prefix="/api/icp", tags=["ICP & Discovery Legacy"], dependencies=_auth_dependency)
app.include_router(inbox.router, prefix="/api/inbox", tags=["Inbox Legacy"], dependencies=_auth_dependency)
app.include_router(lists.router, prefix="/api/lists", tags=["Saved Lists Legacy"], dependencies=_auth_dependency)
app.include_router(suppression.router, prefix="/api/suppression", tags=["Suppression Legacy"], dependencies=_auth_dependency)
app.include_router(setup.router, prefix="/api/setup", tags=["Setup Legacy"], dependencies=_auth_dependency)

@app.get("/health")
async def health_check():
    """Liveness + database connectivity.

    The old version reported the database *scheme* and never touched the
    connection, so a healthcheck passed against a database that was gone.
    """
    db_ok = True
    db_error = None
    try:
        async with async_session_maker() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on the environment
        db_ok = False
        db_error = str(exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "LeadForge Autonomous Outreach Engine",
        "database": settings.DATABASE_URL.split("://")[0],
        "database_reachable": db_ok,
        "auth_enabled": auth_enabled(),
        **({"database_error": db_error} if db_error else {}),
    }
