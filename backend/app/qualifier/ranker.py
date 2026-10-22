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


def _matches_structured_criteria(business: Business, icp_profile: Any) -> bool:
    """The ICP's company-shape criteria: size, turnover, tier, state.

    Keywords say what a business is *called*; these say what it *looks
    like*, which is the part an operator sets from a sales conversation
    ("11-50 staff, over 10Cr turnover, tier-2 cities"). Without them the
    ICP could only be expressed as a word list, which is the one thing a
    salesperson cannot do.
    """
    min_emp = getattr(icp_profile, "min_employees", None)
    if min_emp is not None:
        count = getattr(business, "employee_count", None)
        if count is None or count < min_emp:
            return False

    max_emp = getattr(icp_profile, "max_employees", None)
    if max_emp is not None:
        count = getattr(business, "employee_count", None)
        if count is None or count > max_emp:
            return False

    bands = getattr(icp_profile, "revenue_bands", None) or []
    if bands:
        if (getattr(business, "revenue_band", None) or "") not in bands:
            return False

    buckets = getattr(icp_profile, "size_buckets", None) or []
    if buckets:
        if (getattr(business, "size_bucket", None) or "") not in buckets:
            return False

    tiers = getattr(icp_profile, "market_tiers", None) or []
    if tiers:
        tier = (getattr(business, "market_tier", None) or "").lower()
        if tier not in [str(t).lower() for t in tiers]:
            return False

    states = getattr(icp_profile, "states", None) or []
    if states:
        state = (getattr(business, "state", None) or "").lower()
        if state not in [str(s).lower() for s in states]:
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
        "social_profiles": [
            {
                "platform": p.platform,
                "url": p.url,
                "handle": p.handle,
                "followers": p.followers,
                "posts_count": p.posts_count,
                "verified": bool(p.verified),
                "source": p.source,
            }
            for p in (getattr(business, "social_profiles", None) or [])
        ],
        "score": scoring["score"],
        "tier": scoring["tier"],
        "badges": scoring["badges"],
        "signal_breakdown": scoring["signal_breakdown"],
        "signals": scoring["signals"],
        "source_trust": scoring.get("source_trust"),
        "trust_modifier": scoring.get("trust_modifier", 0),
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
        if not _matches_structured_criteria(business, icp_profile):
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
    """Ranks the leads already in the database against the given ICP profile.

    The previous implementation loaded *every* business in the database
    (``select(Business)`` with no limit) and then scored them in Python.
    Benchmarked at 100k businesses / 100k contacts that was 13.6 seconds and
    837 MB of peak allocation to return 50 rows - and because the scoring
    loop contains no ``await``, it blocked the event loop for the whole
    duration. Extrapolated to 500k rows it was ~70 seconds and ~4 GB per
    request.

    Now the candidate set is bounded in SQL and only the survivors are scored.
    """
    stmt = select(Business).options(
        selectinload(Business.contacts),
        selectinload(Business.social_profiles),
    )
    if scope_icp and getattr(icp_profile, "id", None) is not None:
        stmt = stmt.where(Business.icp_profile_id == icp_profile.id)
    # Over-fetch a bounded window rather than the whole table. Scoring happens
    # in Python (it depends on an ICP's weight table), so the window has to be
    # wide enough to find the best N, but it must never be unbounded.
    stmt = stmt.order_by(Business.id.desc()).limit(max(limit * 20, 200))

    res = await db.execute(stmt)
    businesses = list(res.scalars().all())

    contacts_by_business: Dict[int, List[Contact]] = {
        business.id: list(business.contacts) for business in businesses
    }

    return rank_businesses(businesses, contacts_by_business, icp_profile, limit=limit)
