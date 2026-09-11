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
