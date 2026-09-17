from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business
from app.models.contact import Contact
from .scorer import score_lead


def _matches_icp(business: Business, icp_profile: Any) -> bool:
    """Keyword include/exclude filter driven by the ICP profile."""
    haystack = " ".join(
        str(getattr(business, attr, "") or "")
        for attr in ("name", "industry", "address")
    ).lower()

    keywords = getattr(icp_profile, "keywords", None) or []
    if keywords:
        if not any(k.lower() in haystack for k in keywords):
            return False

    excludes = getattr(icp_profile, "exclude_keywords", None) or []
    for ex in excludes:
        token = str(ex).lower().strip()
        if token and token in haystack:
            return False

    return True


def _lead_payload(business: Business, contacts: List[Contact], scoring: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "business_id": business.id,
        "name": business.name,
        "industry": business.industry,
        "address": business.address,
        "phone": business.phone,
        "website": business.website,
        "rating": business.rating,
        "reviews_count": business.reviews_count,
        "latitude": business.latitude,
        "longitude": business.longitude,
        "source": business.source,
        "contacts": [
            {
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "title": c.title,
                "email": c.email,
                "phone": c.phone,
                "whatsapp_link": c.whatsapp_link,
                "social_links": c.social_links,
                "is_verified": bool(c.is_verified),
                "verification_status": c.verification_status,
            }
            for c in contacts
        ],
        "score": scoring["score"],
        "tier": scoring["tier"],
        "badges": scoring["badges"],
        "signal_breakdown": scoring["signal_breakdown"],
        "signals": scoring["signals"],
    }


def rank_businesses(
    businesses: List[Business],
    contacts_by_business: Dict[int, List[Contact]],
    icp_profile: Any,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Pure ranking pass over already-loaded leads."""
    min_score = getattr(icp_profile, "min_score", None)
    if min_score is None:
        min_score = 45

    ranked: List[Dict[str, Any]] = []
    for business in businesses:
        if not _matches_icp(business, icp_profile):
            continue
        contacts = contacts_by_business.get(business.id, [])
        scoring = score_lead(business, contacts, icp_profile)
        if scoring["score"] < min_score:
            continue
        ranked.append(_lead_payload(business, contacts, scoring))

    ranked.sort(key=lambda lead: lead["score"], reverse=True)
    return ranked[:limit]


async def rank_existing(
    db: AsyncSession,
    icp_profile: Any,
    limit: int = 50,
    scope_icp: bool = False,
) -> List[Dict[str, Any]]:
    """Ranks the leads already in the database against the given ICP profile."""
    stmt = select(Business).options(selectinload(Business.contacts))
    if scope_icp and getattr(icp_profile, "id", None) is not None:
        stmt = stmt.where(Business.icp_profile_id == icp_profile.id)
    stmt = stmt.order_by(Business.id.desc())

    res = await db.execute(stmt)
    businesses = list(res.scalars().all())

    contacts_by_business: Dict[int, List[Contact]] = {
        business.id: list(business.contacts) for business in businesses
    }

    return rank_businesses(businesses, contacts_by_business, icp_profile, limit=limit)
