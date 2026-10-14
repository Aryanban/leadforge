from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import asyncio
import contextlib
import logging

from app.config import settings
from typing import Optional, Any, Dict, List
from app.api import scraper, leads, enricher, campaigns, analytics, mailboxes, icp, inbox, lists, suppression
from app.campaigns import tracker
from app.database import Base, engine
from app.seeds import seed_initial_data_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadforge")

#: How often the in-process reply poller sweeps IMAP (single-process
#: self-host default). Users on Celery get the same cadence via beat — see
#: app/workers/beat_schedule.py — and this loop disables itself when
#: USE_CELERY is true so sends are never double-counted.
REPLY_POLL_INTERVAL_SECONDS = 300


def _sync_missing_columns(sync_conn) -> None:
    """Additive migration: ALTER TABLE ADD COLUMN for any model column the live
    database lacks.

    Replaces a hand-maintained SQL list that drifted every time a column was
    added (and once silently no-op'd for an entire session because `text` was
    not imported). Deriving from the models means a new column needs no
    migration bookkeeping, which is what self-hosted users actually need.

    Only adds columns - never drops or retypes - so it is safe to run on every
    boot. Missing tables are left to ``create_all``.
    """
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    dialect = sync_conn.dialect

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(dialect)}'
            default = getattr(col.default, "arg", None)
            if default is not None and not callable(default):
                ddl += f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {default}"
            try:
                sync_conn.execute(text(ddl))
                logger.info("schema sync: added %s.%s", table.name, col.name)
            except Exception as exc:  # pragma: no cover - dialect-specific limits
                logger.warning("schema sync skipped %s.%s: %s", table.name, col.name, exc)

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing LeadForge database schemas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_missing_columns)

    # Auto-seed initial realistic demo data if database is fresh
    try:
        await seed_initial_data_if_empty()
    except Exception as e:
        logger.warning(f"Seed initialization notice: {e}")

    poller: Optional[asyncio.Task] = None
    if not settings.USE_CELERY:
        poller = asyncio.ensure_future(_reply_poll_loop())

    yield

    if poller is not None:
        poller.cancel()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Versioned API routes (/api/v1/...)
app.include_router(analytics.router, prefix=f"{settings.API_V1_STR}/analytics", tags=["Analytics"])
app.include_router(scraper.router, prefix=f"{settings.API_V1_STR}/scraper", tags=["Scraper"])
app.include_router(leads.router, prefix=f"{settings.API_V1_STR}/leads", tags=["Leads"])
app.include_router(enricher.router, prefix=f"{settings.API_V1_STR}/enricher", tags=["Enrichment"])
app.include_router(campaigns.router, prefix=f"{settings.API_V1_STR}/campaigns", tags=["Campaigns"])
app.include_router(tracker.router, prefix=f"{settings.API_V1_STR}/campaigns/tracker", tags=["Campaign Tracker"])
app.include_router(mailboxes.router, prefix=f"{settings.API_V1_STR}/mailboxes", tags=["Mailboxes"])
app.include_router(icp.router, prefix=f"{settings.API_V1_STR}/icp", tags=["ICP & Discovery"])
app.include_router(inbox.router, prefix=f"{settings.API_V1_STR}/inbox", tags=["Inbox"])
app.include_router(lists.router, prefix=f"{settings.API_V1_STR}/lists", tags=["Saved Lists"])
app.include_router(suppression.router, prefix=f"{settings.API_V1_STR}/suppression", tags=["Suppression"])

# Aliases without /v1 for backwards compatibility (/api/...)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics Legacy"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper Legacy"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads Legacy"])
app.include_router(enricher.router, prefix="/api/enricher", tags=["Enrichment Legacy"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns Legacy"])
app.include_router(mailboxes.router, prefix="/api/mailboxes", tags=["Mailboxes Legacy"])
app.include_router(icp.router, prefix="/api/icp", tags=["ICP & Discovery Legacy"])
app.include_router(inbox.router, prefix="/api/inbox", tags=["Inbox Legacy"])
app.include_router(lists.router, prefix="/api/lists", tags=["Saved Lists Legacy"])
app.include_router(suppression.router, prefix="/api/suppression", tags=["Suppression Legacy"])

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "LeadForge Autonomous Outreach Engine",
        "database": settings.DATABASE_URL.split("://")[0]
    }
