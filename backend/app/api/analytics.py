from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, Any

from app.database import get_db
from app.models.business import Business
from app.models.contact import Contact
from app.models.send import Send
from app.models.campaign import Campaign
from app.models.scrape_job import ScrapeJob

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
