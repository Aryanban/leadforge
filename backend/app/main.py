from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import contextlib
import logging

from app.config import settings
from app.api import scraper, leads, enricher, campaigns, analytics, mailboxes, icp
from app.campaigns import tracker
from app.database import Base, engine
from app.seeds import seed_initial_data_if_empty

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadforge")

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing LeadForge database schemas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive column migrations for pre-existing SQLite installs.
        for stmt in (
            "ALTER TABLE businesses ADD COLUMN maps_url TEXT;",
            "ALTER TABLE businesses ADD COLUMN source TEXT;",
            "ALTER TABLE businesses ADD COLUMN icp_profile_id INTEGER REFERENCES icp_profiles(id);",
            "ALTER TABLE businesses ADD COLUMN icp_fit JSON;",
            "ALTER TABLE scrape_jobs ADD COLUMN result JSON;",
            "ALTER TABLE scrape_jobs ADD COLUMN icp_profile_id INTEGER;",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass
    
    # Auto-seed initial realistic demo data if database is fresh
    try:
        await seed_initial_data_if_empty()
    except Exception as e:
        logger.warning(f"Seed initialization notice: {e}")

    yield
    logger.info("LeadForge shutting down.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Autonomous lead generation, contact enrichment, and cold email outreach engine.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS middleware for Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Aliases without /v1 for backwards compatibility (/api/...)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics Legacy"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["Scraper Legacy"])
app.include_router(leads.router, prefix="/api/leads", tags=["Leads Legacy"])
app.include_router(enricher.router, prefix="/api/enricher", tags=["Enrichment Legacy"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns Legacy"])
app.include_router(mailboxes.router, prefix="/api/mailboxes", tags=["Mailboxes Legacy"])
app.include_router(icp.router, prefix="/api/icp", tags=["ICP & Discovery Legacy"])

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "LeadForge Autonomous Outreach Engine",
        "database": settings.DATABASE_URL.split("://")[0]
    }
