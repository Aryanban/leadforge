import urllib.parse
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, or_
from typing import Dict, Any, List, Optional
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

#: The reply categories that count as a positive outcome. Kept in step with
#: the A/B winner's definition, so "Interested" means the same thing in the
#: funnel as it does in a subject-line test.
POSITIVE_REPLY_CATEGORIES = ("interested",)

@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    # 1. Total Businesses - split into real leads and the sample rows a fresh
    #    database is seeded with. Reporting "83 businesses in your database"
    #    when those 83 are demo data the operator never found is the first
    #    thing the product says to a new user, and it is not true.
    res_b = await db.execute(
        select(
            func.count(Business.id),
            func.count(Business.id).filter(Business.is_demo == True),
            func.count(Business.id).filter(
                or_(Business.is_demo == False, Business.is_demo.is_(None))
            ),
        )
    )
    total_leads, demo_leads, real_leads = res_b.one()
    total_leads = total_leads or 0
    demo_leads = demo_leads or 0
    real_leads = real_leads or 0

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
        "real_leads": real_leads,
        "demo_leads": demo_leads,
        "total_contacts": total_contacts,
        "verified_contacts": verified_contacts,
        "emails_sent": sent_count,
        "emails_opened": opened_count,
        "open_rate": open_rate,
        "active_campaigns": active_campaigns,
        "recent_leads": recent_leads,
        "recent_jobs": recent_jobs
    }


@router.get("/funnel")
async def get_funnel(
    days: int = Query(90, ge=7, le=730),
    include_demo: bool = Query(
        True, description="Include the sample rows a fresh database is seeded with."
    ),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """The pipeline, stage by stage.

    The dashboard used to show four flat counters - businesses, contacts,
    verified, sent - which cannot answer the only question that matters:
    *where does the pipeline leak?* A list of 500 businesses that produced
    12 emails and 1 reply looks the same as a list of 12 businesses that
    produced 1 email and 1 reply, and the operator cannot tell which part
    to fix.

    Every stage is a real predicate over the data, and each stage's rate
    is relative to the one before it, so the drop-off is visible.
    """
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(days=days)

    demo_clause = [] if include_demo else [
        or_(Business.is_demo == False, Business.is_demo.is_(None))
    ]

    # --- stage 1: businesses discovered ------------------------------------
    res = await db.execute(
        select(func.count(Business.id)).where(*demo_clause)
    )
    discovered = res.scalar() or 0

    # --- stage 2: a business with a reachable phone ------------------------
    res = await db.execute(
        select(func.count(Business.id)).where(
            *demo_clause, Business.phone.isnot(None), Business.phone != ""
        )
    )
    with_phone = res.scalar() or 0

    # --- stage 3: a contact with an email address --------------------------
    res = await db.execute(
        select(func.count(func.distinct(Contact.business_id)))
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Contact.email.isnot(None), Contact.email != "")
    )
    with_email = res.scalar() or 0

    # --- stage 4: an email that verified as deliverable ---------------------
    res = await db.execute(
        select(func.count(func.distinct(Contact.business_id)))
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Contact.is_verified == True)
    )
    verified = res.scalar() or 0

    # --- stage 5: targeted in a campaign -----------------------------------
    res = await db.execute(
        select(func.count(func.distinct(Send.contact_id)))
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Send.created_at >= since)
    )
    targeted = res.scalar() or 0

    # --- stage 6: actually sent --------------------------------------------
    res = await db.execute(
        select(func.count(Send.id))
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Send.status == "sent", func.coalesce(Send.sent_at, Send.created_at) >= since)
    )
    sent = res.scalar() or 0

    # --- stage 7: opened ----------------------------------------------------
    res = await db.execute(
        select(func.count(Send.id))
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Send.status == "sent", Send.opened == True,
               func.coalesce(Send.sent_at, Send.created_at) >= since)
    )
    opened = res.scalar() or 0

    # --- stage 8: replied ---------------------------------------------------
    res = await db.execute(
        select(func.count(Send.id))
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(*demo_clause, Send.replied == True, func.coalesce(Send.sent_at, Send.created_at) >= since)
    )
    replied = res.scalar() or 0

    # --- stage 9: a positive reply ------------------------------------------
    res = await db.execute(
        select(func.count(Send.id))
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(
            *demo_clause, Send.replied == True, func.coalesce(Send.sent_at, Send.created_at) >= since,
            Send.reply_category.in_(POSITIVE_REPLY_CATEGORIES),
        )
    )
    positive = res.scalar() or 0

    stages = [
        {"key": "discovered", "label": "Businesses found", "count": discovered,
         "hint": "Every business in the database"},
        {"key": "phone", "label": "With a phone", "count": with_phone,
         "hint": "Reachable on a call or WhatsApp"},
        {"key": "email", "label": "With an email", "count": with_email,
         "hint": "An address was found for the business"},
        {"key": "verified", "label": "Verified email", "count": verified,
         "hint": "The address passed deliverability checks"},
        {"key": "targeted", "label": "In a sequence", "count": targeted,
         "hint": f"Targeted in the last {days} days"},
        {"key": "sent", "label": "Emails sent", "count": sent,
         "hint": f"Delivered in the last {days} days"},
        {"key": "opened", "label": "Opened", "count": opened,
         "hint": "The recipient opened it"},
        {"key": "replied", "label": "Replied", "count": replied,
         "hint": "Any reply at all"},
        {"key": "positive", "label": "Interested", "count": positive,
         "hint": "A reply the operator can act on"},
    ]

    def _rate(numerator: int, denominator: int) -> Optional[float]:
        if not denominator:
            return None
        return round((numerator / denominator) * 100, 1)

    # --- where the leads came from -----------------------------------------
    source_rows = (await db.execute(
        select(Business.source, func.count(Business.id))
        .where(*demo_clause)
        .group_by(Business.source)
        .order_by(func.count(Business.id).desc())
        .limit(15)
    )).all()
    by_source = [
        {"source": source or "unknown", "count": count}
        for source, count in source_rows
    ]

    # --- reply categories ---------------------------------------------------
    category_rows = (await db.execute(
        select(Send.reply_category, func.count(Send.id))
        .where(Send.replied == True, func.coalesce(Send.sent_at, Send.created_at) >= since)
        .group_by(Send.reply_category)
    )).all()
    reply_categories = [
        {"category": category or "uncategorised", "count": count}
        for category, count in category_rows
    ]

    # --- per mailbox --------------------------------------------------------
    mailbox_rows = (await db.execute(
        select(Mailbox.email, func.count(Send.id),
               func.count(Send.id).filter(Send.opened == True),
               func.count(Send.id).filter(Send.replied == True),
               func.count(Send.id).filter(Send.bounced == True))
        .join(Send, Send.mailbox_id == Mailbox.id)
        .where(Send.status == "sent", func.coalesce(Send.sent_at, Send.created_at) >= since)
        .group_by(Mailbox.email)
        .order_by(func.count(Send.id).desc())
    )).all()
    by_mailbox = [
        {
            "email": email,
            "sent": sent,
            "opened": opened,
            "replied": replied,
            "bounced": bounced,
            "open_rate": _rate(opened, sent),
            "reply_rate": _rate(replied, sent),
            "bounce_rate": _rate(bounced, sent),
        }
        for email, sent, opened, replied, bounced in mailbox_rows
    ]

    return {
        "days": days,
        "stages": stages,
        "rates": {
            "phone": _rate(with_phone, discovered),
            "email": _rate(with_email, with_phone),
            "verified": _rate(verified, with_email),
            "sent": _rate(sent, targeted),
            "open": _rate(opened, sent),
            "reply": _rate(replied, sent),
            "positive": _rate(positive, replied),
        },
        "by_source": by_source,
        "by_mailbox": by_mailbox,
        "reply_categories": reply_categories,
    }


@router.get("/timeseries")
async def get_timeseries(days: int = 30, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Per-day send activity for charts: sent / opened / replied / bounced.

    The aggregation happens in SQL. It used to load every Send row in the
    window into Python and count them there, which meant a busy account
    (100k sends in 30 days) materialised 100k ORM objects just to produce
    thirty numbers.

    ``CAST(sent_at AS DATE)`` keeps one code path for SQLite and Postgres.
    Missing days are zero-filled in Python so charts never gap on idle days
    (a gap reads identically to a zero-send day, which it always is here).
    """
    days = max(1, min(days, 365))
    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)

    # ``date()`` is the portable day-truncation function: SQLite has
    # ``date(x)`` and Postgres has ``date(timestamp)``. A ``CAST(x AS DATE)``
    # is NOT portable - SQLite applies NUMERIC affinity to the cast and
    # truncates '2026-10-17' to the integer 2026, which then blows up in
    # SQLAlchemy's date processor.
    day_col = func.date(Send.sent_at).label("day")
    rows = (await db.execute(
        select(
            day_col,
            func.count(Send.id),
            func.sum(case((Send.opened == True, 1), else_=0)),
            func.sum(case((Send.replied == True, 1), else_=0)),
            func.sum(case((Send.status == "bounced", 1), else_=0)),
        )
        .where(
            Send.status == "sent",
            Send.sent_at.isnot(None),
            Send.sent_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
        )
        .group_by(day_col)
    )).all()

    by_day: Dict[str, Dict[str, int]] = {}
    for day, sent, opened, replied, bounced in rows:
        if day is None:
            continue
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        by_day[key] = {
            "sent": int(sent or 0),
            "opened": int(opened or 0),
            "replied": int(replied or 0),
            "bounced": int(bounced or 0),
        }

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
