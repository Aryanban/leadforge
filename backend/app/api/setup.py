"""Setup & connections status — the payload for the Connections page.

One endpoint answers "is this instance fully functional?": what the user
still needs to connect, what's already good, and which environment knobs
deserve attention (TRACKING_DOMAIN on a remote deploy, proxy coverage for
scraping volume, a placeholder secret in production posture).

Deliberately read-only: every action (add mailbox, set IMAP, test SMTP,
poll replies) lives on the existing endpoints this page links to.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.mailbox import Mailbox

router = APIRouter()

#: The placeholder the app refuses to boot with when ENV=production.
PLACEHOLDER_SECRET = "leadforge-secret-key-production-change-me"

#: Where runtime settings are persisted. Tests monkeypatch this to a tmp file
#: so the real backend/.env is never touched by the suite.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

#: Settings the dashboard may change at runtime, with plain-language rules.
#: - TRACKING_DOMAIN applies immediately (read per-send for unsubscribe links).
#: - PROXY_LIST applies immediately (read per request by the scraper).
#: - CORS_ORIGINS is baked into the middleware at boot -> restart required.
RUNTIME_SETTINGS: Dict[str, Dict[str, Any]] = {
    "TRACKING_DOMAIN": {
        "label": "Public backend URL (unsubscribe links)",
        "placeholder": "https://api.yourdomain.com",
        "restart_required": False,
    },
    "PROXY_LIST": {
        "label": "Rotating proxies for scraping",
        "placeholder": "http://user:pass@ip:port,http://user:pass@ip2:port",
        "restart_required": False,
    },
    "CORS_ORIGINS": {
        "label": "Allowed dashboard origins",
        "placeholder": "https://app.yourdomain.com",
        "restart_required": True,
    },
}

#: Non-technical provider presets: SMTP/IMAP hosts + exactly where the app
#: password lives. Sourced from the Connections wizard so a first-time user
#: never has to know what a "host" is.
PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "gmail",
        "label": "Gmail / Google Workspace",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "howto": "Open myaccount.google.com → Security → 2-Step Verification (turn it on) → "
                 "App passwords → create one for 'Mail'. Paste the 16-character password here "
                 "(your normal Google password will NOT work).",
    },
    {
        "id": "outlook",
        "label": "Outlook / Hotmail / Microsoft 365",
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "howto": "Microsoft 365: admin must enable 'SMTP AUTH' (Microsoft 365 admin center → "
                 "Users → your user → Mail → 'Manage email apps'). Personal Outlook: enable "
                 "two-step verification then create an app password at account.microsoft.com.",
    },
    {
        "id": "zoho",
        "label": "Zoho Mail",
        "smtp_host": "smtp.zoho.com",
        "smtp_port": 465,
        "imap_host": "imap.zoho.com",
        "imap_port": 993,
        "howto": "Zoho Mail → Settings → Mail Accounts → IMAP → enable IMAP; use your Zoho "
                 "account password or an app-specific password (accounts.zoho.com → "
                 "Security → App Passwords).",
    },
    {
        "id": "yahoo",
        "label": "Yahoo Mail",
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "howto": "Turn on two-step verification in account security, then create an app "
                 "password at login.yahoo.com → Account Security → Generate app password. "
                 "Paste that here (not your Yahoo password).",
    },
    {
        "id": "custom",
        "label": "Other provider (custom SMTP)",
        "smtp_host": "",
        "smtp_port": 587,
        "imap_host": "",
        "imap_port": 993,
        "howto": "Your provider's docs will list an 'SMTP host' and 'port' (often "
                 "smtp.yourdomain.com:587) — paste them below. Use an app password if 2FA is on.",
    },
]


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
        # Current values of the settings the Connections page can edit in-place.
        "runtime_settings": {
            key: {
                "value": str(getattr(settings, key, "")),
                "label": spec["label"],
                "placeholder": spec["placeholder"],
                "restart_required": spec["restart_required"],
            }
            for key, spec in RUNTIME_SETTINGS.items()
        },
    }


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.get("/providers")
async def list_providers() -> Dict[str, Any]:
    """SMTP/IMAP presets with plain-English 'where is my app password' help.

    Sourced server-side so the wizard and the Settings page speak with one
    voice; a non-technical user picks their provider and never touches a host
    field (the preset fills SMTP/IMAP hosts and ports).
    """
    return {"providers": PROVIDERS}


def _persist_env_file(key: str, value: str) -> None:
    """Writes KEY=value into backend/.env, preserving every other line.

    Only called for the RUNTIME_SETTINGS allowlist — the app never touches
    secrets or arbitrary keys. The file lives next to the backend package so
    it works for bare-metal runs and inside the Docker image alike.
    """
    line = f"{key}={value}"
    lines: List[str] = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, existing in enumerate(lines):
        if existing.split("=", 1)[0].strip() == key:
            lines[i] = line
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(line)
    _ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.put("/settings")
async def update_runtime_setting(req: SettingUpdate) -> Dict[str, Any]:
    """Applies a runtime setting: live immediately + persisted to .env.

    The dashboard writes nothing to disk itself; this is the single, validated
    door. Validation is deliberately strict for TRACKING_DOMAIN — a typo here
    breaks every unsubscribe link a recipient might click.
    """
    spec = RUNTIME_SETTINGS.get(req.key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"'{req.key}' is not editable at runtime")

    value = (req.value or "").strip()
    if req.key == "TRACKING_DOMAIN":
        if value and not value.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=422,
                detail="The public URL must start with http:// or https://",
            )
        value = value.rstrip("/")
    elif req.key == "CORS_ORIGINS" and value and value != "*":
        for origin in [o.strip() for o in value.split(",") if o.strip()]:
            if not origin.startswith(("http://", "https://")):
                raise HTTPException(
                    status_code=422,
                    detail=f"'{origin}' is not a valid origin — use e.g. https://app.example.com",
                )

    setattr(settings, req.key, value if value else ("*" if req.key == "CORS_ORIGINS" else ""))
    try:
        _persist_env_file(req.key, value)
        persisted = True
    except OSError:  # read-only fs (rare) — live apply still worked
        persisted = False

    return {
        "key": req.key,
        "value": getattr(settings, req.key),
        "persisted": persisted,
        "restart_required": bool(spec["restart_required"]),
        "label": spec["label"],
    }
