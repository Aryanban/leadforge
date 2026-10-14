import urllib.parse
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, Any
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.business import Business
from app.models.contact import Contact
from app.models.send import Send
from app.models.campaign import Campaign
from app.models.scrape_job import ScrapeJob
from app.models.mailbox import Mailbox
from app.models.suppression import Suppression

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    # 1. Total Businesses
    res_b = await db.execute(select(func.count(Business.id)))
    total_leads = res_b.scalar() or 0

    # 2. Total Contacts
    res_c = await db.execute(select(func.count(Contact.id)))
    total_contacts = res_c.scalar() or 0

    # 3. Verified Contacts
    res_v = await db.execute(select(func.count(Contact.id)).where(Contact.is_verified == True))
    verified_contacts = res_v.scalar() or 0

    # 4. Total Sends & Opens
    res_s = await db.execute(
        select(
            func.count(Send.id),
            func.count(Send.id).filter(Send.status == "sent"),
            func.count(Send.id).filter(Send.opened == True)
        )
    )
    total_sends, sent_count, opened_count = res_s.one()
    open_rate = round((opened_count / sent_count * 100), 1) if sent_count > 0 else 0.0

    # 5. Active Campaigns
    res_camp = await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "active"))
    active_campaigns = res_camp.scalar() or 0

    # 6. Recent Leads (5)
    recent_leads_res = await db.execute(select(Business).order_by(Business.created_at.desc()).limit(5))
    recent_businesses = recent_leads_res.scalars().all()

    # Get contacts for recent businesses
    recent_b_ids = [b.id for b in recent_businesses]
    contacts_lookup = {}
    if recent_b_ids:
        c_res = await db.execute(select(Contact).where(Contact.business_id.in_(recent_b_ids)))
        for c in c_res.scalars().all():
            if c.business_id not in contacts_lookup:
                contacts_lookup[c.business_id] = c

    recent_leads = [
        {
            "id": b.id,
            "name": b.name,
            "industry": b.industry or "General",
            "phone": b.phone or (contacts_lookup.get(b.id).phone if b.id in contacts_lookup else None),
            "email": contacts_lookup.get(b.id).email if b.id in contacts_lookup else None,
            "is_verified": contacts_lookup.get(b.id).is_verified if b.id in contacts_lookup else False,
            "rating": b.rating,
            "maps_url": b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}",
            "created_at": b.created_at.isoformat() if b.created_at else None
        }
        for b in recent_businesses
    ]

    # 7. Recent Scrape Jobs (5)
    jobs_res = await db.execute(select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(5))
    recent_jobs = [
        {
            "id": j.id,
            "query": j.query,
            "status": j.status,
            "total_found": j.total_found,
            "leads_saved": j.leads_saved,
            "created_at": j.created_at.isoformat() if j.created_at else None
        }
        for j in jobs_res.scalars().all()
    ]

    return {
        "total_leads": total_leads,
        "total_contacts": total_contacts,
        "verified_contacts": verified_contacts,
        "emails_sent": sent_count,
        "emails_opened": opened_count,
        "open_rate": open_rate,
        "active_campaigns": active_campaigns,
        "recent_leads": recent_leads,
        "recent_jobs": recent_jobs
    }


@router.get("/timeseries")
async def get_timeseries(days: int = 30, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Per-day send activity for charts: sent / opened / replied / bounced.

    ``CAST(sent_at AS DATE)`` keeps one code path for SQLite and Postgres.
    Missing days are zero-filled in Python so charts never gap on idle days
    (a gap reads identically to a zero-send day, which it always is here).
    """
    days = max(1, min(days, 365))
    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)

    rows = (await db.execute(
        select(Send).where(
            Send.status == "sent",
            Send.sent_at.isnot(None),
            Send.sent_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
        )
    )).scalars().all()

    by_day: Dict[str, Dict[str, int]] = {}
    for s in rows:
        key = s.sent_at.date().isoformat()
        cell = by_day.setdefault(key, {"sent": 0, "opened": 0, "replied": 0, "bounced": 0})
        cell["sent"] += 1
        if s.opened:
            cell["opened"] += 1
        if s.replied:
            cell["replied"] += 1
        if getattr(s, "status", None) == "bounced":
            cell["bounced"] += 1

    series = []
    for i in range(days):
        key = (start + timedelta(days=i)).isoformat()
        cell = by_day.get(key, {"sent": 0, "opened": 0, "replied": 0, "bounced": 0})
        series.append({"date": key, **cell})

    totals = {k: sum(d[k] for d in series) for k in ("sent", "opened", "replied", "bounced")}
    sent = totals["sent"] or 1
    totals["reply_rate"] = round(totals["replied"] / sent * 100, 1)
    totals["open_rate"] = round(totals["opened"] / sent * 100, 1)
    return {"days": series, "totals": totals, "period_days": days}


@router.get("/tasks")
async def get_tasks(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Computed to-do list (Apollo home widget): actionable state, no storage.

    Every item is a link-shaped {key, label, count, severity, href} so the
    dashboard renders a checklist straight from real database state.
    """
    tasks = []

    no_mailbox = (await db.execute(select(func.count(Mailbox.id)))).scalar() or 0
    if no_mailbox == 0:
        tasks.append({"key": "mailbox", "label": "Add your first sending mailbox",
                      "count": 0, "severity": "high", "href": "/settings"})

    unverified = (await db.execute(
        select(func.count(Contact.id)).where(
            Contact.email.isnot(None),
            Contact.is_verified == False,
            Contact.unsubscribed == False,
        )
    )).scalar() or 0
    if unverified:
        tasks.append({"key": "verify", "label": f"{unverified} contacts await verification",
                      "count": unverified, "severity": "medium", "href": "/leads"})

    pending_reply = (await db.execute(
        select(func.count(Send.id)).where(Send.replied == True)
    )).scalar() or 0
    if pending_reply:
        tasks.append({"key": "replies", "label": f"{pending_reply} replies to triage in the Inbox",
                      "count": pending_reply, "severity": "high", "href": "/inbox"})

    paused_mb = (await db.execute(
        select(func.count(Mailbox.id)).where(Mailbox.health_paused == True)
    )).scalar() or 0
    if paused_mb:
        tasks.append({"key": "mailbox_health", "label": f"{paused_mb} mailbox(es) health-paused — needs review",
                      "count": paused_mb, "severity": "high", "href": "/email-health"})

    suppressed = (await db.execute(
        select(func.count(Suppression.id))
    )).scalar() or 0
    tasks.append({"key": "suppression", "label": f"{suppressed} address(es) on the global suppression list",
                  "count": suppressed, "severity": "info", "href": "/settings"})

    return {"tasks": tasks}
