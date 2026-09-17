import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob

from .match import find_existing_business, normalize_phone

logger = logging.getLogger(__name__)


async def persist_raw_leads(
    db: AsyncSession,
    raw_leads: List[dict],
    icp_profile_id: Optional[int],
    job_id: Optional[int] = None,
) -> List[int]:
    """
    Inserts only genuinely new businesses (dedupe-aware) and their seed contacts.

    Returns the IDs of the businesses created by this call — enrichment and
    ranking only ever consider these fresh leads.
    """
    new_ids: List[int] = []
    duplicates = 0

    for lead in raw_leads:
        name = (lead.get("name") or "").strip()
        if not name:
            continue

        existing = await find_existing_business(db, lead)
        if existing:
            duplicates += 1
            if icp_profile_id and not existing.icp_profile_id:
                existing.icp_profile_id = icp_profile_id
            if not existing.source and lead.get("source"):
                existing.source = lead.get("source")
            continue

        business = Business(
            place_id=lead.get("place_id"),
            name=name,
            website=lead.get("website") or None,
            phone=lead.get("phone") or None,
            address=lead.get("address") or None,
            maps_url=lead.get("maps_url") or None,
            rating=lead.get("rating"),
            reviews_count=lead.get("reviews_count"),
            industry=lead.get("industry"),
            latitude=lead.get("latitude"),
            longitude=lead.get("longitude"),
            source=lead.get("source"),
            icp_profile_id=icp_profile_id,
            extra_data={
                "query": lead.get("query"),
                "scraped_at": datetime.utcnow().isoformat(),
                "is_claimed": lead.get("is_claimed", True),
                "operational_status": lead.get("operational_status"),
                "price_tier": lead.get("price_tier"),
            },
        )
        db.add(business)
        await db.flush()

        clean_phone = normalize_phone(lead.get("phone"))
        contact = Contact(
            business_id=business.id,
            first_name=name.split()[0] if name.split() else "Owner",
            title="Owner / Decision Maker",
            phone=lead.get("phone") or None,
            whatsapp_link=f"https://wa.me/{clean_phone}" if clean_phone else None,
            email=None,
            source=lead.get("source", "discovery"),
            verification_status="unverified",
        )
        db.add(contact)
        new_ids.append(business.id)

    if job_id is not None:
        job = await db.get(ScrapeJob, job_id)
        if job:
            job.total_found = (job.total_found or 0) + len(raw_leads)
            job.leads_saved = (job.leads_saved or 0) + len(new_ids)

    await db.commit()
    if duplicates:
        logger.info(f"Dedupe skipped {duplicates} already-known businesses")
    return new_ids
