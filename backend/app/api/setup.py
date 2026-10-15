"""Setup & connections status — the payload for the Connections page.

One endpoint answers "is this instance fully functional?": what the user
still needs to connect, what's already good, and which environment knobs
deserve attention (TRACKING_DOMAIN on a remote deploy, proxy coverage for
scraping volume, a placeholder secret in production posture).

Deliberately read-only: every action (add mailbox, set IMAP, test SMTP,
poll replies) lives on the existing endpoints this page links to.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.mailbox import Mailbox

router = APIRouter()

#: The placeholder the app refuses to boot with when ENV=production.
PLACEHOLDER_SECRET = "leadforge-secret-key-production-change-me"


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    mailboxes = (await db.execute(select(Mailbox))).scalars().all()
    total_mb = len(mailboxes)
    active_mb = sum(1 for m in mailboxes if m.is_active)
    imap_ready = sum(
        1 for m in mailboxes
        if m.is_active and (m.imap_host or m.smtp_host)
    )
    proxies = [p.strip() for p in (settings.PROXY_LIST or "").split(",") if p.strip()]

    checks: List[Dict[str, Any]] = []

    # 1. Sending mailbox — the hard requirement for outreach.
    ok = total_mb > 0
    checks.append({
        "key": "mailbox",
        "label": "SMTP sending mailbox",
        "required": True,
        "ok": ok,
        "detail": (
            f"{total_mb} mailbox(es), {active_mb} active" if ok
            else "Add a mailbox in Settings — campaigns cannot send without one."
        ),
        "href": "/settings",
    })

    # 2. IMAP reply detection — optional but the reply loop depends on it.
    checks.append({
        "key": "imap",
        "label": "Inbound reply detection (IMAP)",
        "required": False,
        "ok": imap_ready > 0,
        "detail": (
            f"{imap_ready} mailbox(es) will be polled every 5 minutes" if imap_ready
            else "Optional — without IMAP, replies are not detected automatically. "
                 "Gmail-style hosts auto-swap smtp->imap."
        ),
        "href": "/email-health",
    })

    # 3. Tracking domain — unsubscribe links break if this is wrong.
    tracking = settings.TRACKING_DOMAIN or ""
    tracking_ok = bool(tracking) and "localhost" not in tracking
    checks.append({
        "key": "tracking",
        "label": "Tracking domain (unsubscribe links)",
        "required": False,
        "ok": tracking_ok,
        "detail": (
            f"Set to {tracking}" if tracking_ok
            else f"Currently {tracking or 'unset'} — unsubscribe links point to "
                 "localhost, which breaks for recipients on a remote deploy. "
                 "Set TRACKING_DOMAIN in backend/.env to your public URL."
        ),
        "href": None,
    })

    # 4. Proxies — optional, needed at scraping volume.
    checks.append({
        "key": "proxies",
        "label": "Rotating proxies for scraping",
        "required": False,
        "ok": len(proxies) > 0,
        "detail": (
            f"{len(proxies)} proxy URL(s) configured" if proxies
            else "Optional — direct egress rate-limits quickly at sustained "
                 "Google Maps volume. Set PROXY_LIST in backend/.env."
        ),
        "href": None,
    })

    # 5. Secret hygiene. Not send-blocking locally (dev placeholder is fine
    # and the app still boots) — it only gates production posture, so it is
    # advisory in the checklist and required in the env table below.
    secret_ok = settings.SECRET_KEY != PLACEHOLDER_SECRET
    checks.append({
        "key": "secret",
        "label": "API secret key",
        "required": False,
        "ok": secret_ok,
        "detail": (
            "Random secret set" if secret_ok
            else "Placeholder secret in use — fine for local dev; the app refuses "
                 "to boot with this when ENV=production. Generate: openssl rand -hex 32"
        ),
        "href": None,
    })

    required_ok = all(c["ok"] for c in checks if c["required"])
    return {
        "ready": required_ok,
        "db_type": settings.DATABASE_URL.split("://")[0] if settings.DATABASE_URL else "unknown",
        "api_url": settings.TRACKING_DOMAIN,
        "checks": checks,
        "mailboxes": [
            {
                "id": m.id,
                "email": m.email,
                "smtp_host": m.smtp_host,
                "smtp_port": m.smtp_port,
                "daily_limit": m.daily_limit,
                "is_active": m.is_active,
                "imap_host": m.imap_host,
                "imap_port": m.imap_port,
                "health_paused": bool(getattr(m, "health_paused", False)),
            }
            for m in mailboxes
        ],
        "env_keys": [
            {"key": "DATABASE_URL", "required": False,
             "note": "Unset = zero-config SQLite (leadforge.db)"},
            {"key": "SECRET_KEY", "required": True,
             "note": "openssl rand -hex 32 — required when ENV=production"},
            {"key": "ENV", "required": False, "note": "dev | production"},
            {"key": "CORS_ORIGINS", "required": False,
             "note": "Comma-separated dashboard origins; '*' fine locally"},
            {"key": "TRACKING_DOMAIN", "required": False,
             "note": "Public backend URL used in unsubscribe links"},
            {"key": "PROXY_LIST", "required": False,
             "note": "Comma-separated rotating proxies for scraping"},
            {"key": "USE_CELERY", "required": False,
             "note": "true only for Docker/Redis deployments"},
        ],
        "ai_note": (
            "Icebreakers, scoring and copy are generated on-device from industry "
            "templates — no LLM API key or external AI service is required."
        ),
    }
