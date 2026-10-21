from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os


def _require_secret() -> str:
    """Fail fast when the default dev secret reaches a real deployment.

    A leaked/hardcoded JWT secret means anyone can forge auth tokens, so the
    app refuses to boot with the placeholder outside local dev. Set
    SECRET_KEY in the environment (generate with `openssl rand -hex 32`).
    """
    val = os.environ.get("SECRET_KEY", "")
    if not val or val == "leadforge-secret-key-production-change-me":
        if os.environ.get("ENV", "dev") == "production":
            raise RuntimeError(
                "SECRET_KEY must be set to a random value in production "
                "(e.g. `openssl rand -hex 32`). Refusing to boot."
            )
        return "leadforge-secret-key-production-change-me"
    if len(val) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters.")
    return val


class Settings(BaseSettings):
    PROJECT_NAME: str = "LeadForge API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = _require_secret()

    #: Comma-separated list of origins allowed to call the API from a
    #: browser. "*" is convenient locally but lets any website drive your API
    #: with the user's cookies, so production requires an explicit list.
    CORS_ORIGINS: str = "*"

    #: Optional shared secret for the REST API. When unset, the API is open -
    #: which is the right default for a local single-user clone-and-run, and
    #: the wrong default the moment the port is reachable from a LAN. Set
    #: API_KEY and every router except the mail-facing tracker requires it.
    API_KEY: Optional[str] = None

    #: Require the API key even when API_KEY is unset. Useful for a hardened
    #: deployment that generates the key at boot.
    REQUIRE_AUTH: bool = False
    
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

    # --- Cold-email deliverability (see README "Deliverability") -----------
    # Open-tracking pixels are a PRIMARY-INBOX KILLER: a 1x1 remote image
    # fetched from a third-party tracking domain is a commercial-newsletter
    # signal at Gmail / Outlook / Yahoo (2026), and it routes the message to
    # the Promotions or Spam tab. For cold outreach we default this OFF — you
    # sacrifice open-rate telemetry and gain the only metric that matters for
    # cold: landing in the Primary inbox. Enable only for warm/nurture flows
    # where you already have a relationship and the Promotions tab is fine.
    OPEN_TRACKING_ENABLED: bool = False
    # Randomized inter-send jitter. A fixed sleep betrays blast software and
    # gets the whole mailbox throttled; humans do not send on a metronome.
    # Each send waits a random duration in [min, max] seconds. The 2026
    # playbook recommends ~25-60s for a single warm mailbox.
    SEND_JITTER_MIN_SECONDS: int = 20
    SEND_JITTER_MAX_SECONDS: int = 60

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
