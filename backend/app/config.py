from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "LeadForge API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "leadforge-secret-key-production-change-me"
    
    # Database settings
    # Default to sqlite for instant local operation; can be overridden via DATABASE_URL in .env
    DATABASE_URL: Optional[str] = None
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "leadforge"

    # Redis/Celery (optional for distributed scaling)
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_CELERY: bool = False

    # Campaign & Outreach
    TRACKING_DOMAIN: str = "http://localhost:8000"
    DEFAULT_DELAY_SECONDS: int = 15
    MAX_EMAILS_PER_DAY_PER_MAILBOX: int = 50

    # Scraper & Enricher
    PLAYWRIGHT_HEADLESS: bool = True
    ENRICH_MAX_PAGES: int = 4
    REQUEST_TIMEOUT: int = 15
    # Stage-B social enrichment: direct Instagram/Facebook/LinkedIn search.
    # Off by default — these endpoints block scrapers and are ToS-gray.
    SOCIAL_DIRECT: bool = False

    # Discovery fan-out. Sources used to be awaited one at a time, so a run took
    # the SUM of every directory's latency; with these they take the MAX.
    # The cap matters: every source hits the same class of target, and an
    # unbounded fan-out from one IP is what triggers rate-limiting.
    SOURCE_MAX_CONCURRENCY: int = 3
    SOURCE_TIMEOUT_SECONDS: int = 30

    # HTTP hardening for the directory sources. JustDial returns a 14-byte stub
    # and ZaubaCorp a 403 when they dislike the client, so a single attempt with
    # a single User-Agent is not a usable strategy. Retries cost nothing when
    # the first attempt succeeds and rescue an entire source when it does not.
    HTTP_MAX_RETRIES: int = 3
    HTTP_RETRY_BACKOFF: float = 1.5
    # Rotating residential proxies. Comma-separated URLs, e.g.
    # PROXY_LIST=http://user:pass@ip:port,http://user:pass@ip2:port
    # Without these, Google/JustDial scraping from a datacentre IP rate-limits
    # quickly. Empty means direct egress.
    PROXY_LIST: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.DATABASE_URL:
            # If POSTGRES_URL environment variable or postgres host is specifically given
            env_db = os.getenv("DATABASE_URL")
            if env_db:
                self.DATABASE_URL = env_db
            else:
                # Default to local SQLite database file for zero-config Mac/local usage
                self.DATABASE_URL = "sqlite+aiosqlite:///./leadforge.db"

settings = Settings()
