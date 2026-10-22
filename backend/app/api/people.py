"""The People table: one row per human, filterable.

Why this endpoint exists: LeadForge had a *business* table with a nested
contact, and no way to ask the question the product is actually for -
"show me every owner in Pune with a reachable email". Apollo's core
surface is a person per row with attributes you can filter on, and without
that the tool is a business directory with a mailing list attached.

Every filter here is a SQL predicate applied *before* the LIMIT, and the
count query reuses the same predicates, so a filtered page reports an
honest total and every matching row is reachable by paging.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enricher.seniority import (
    DECISION_MAKER_BANDS,
    SENIORITY_LABELS,
    is_decision_maker,
)
from app.models.business import Business
from app.models.contact import Contact

logger = logging.getLogger(__name__)

router = APIRouter()

#: Seniority bands a caller may filter on, in the order the UI shows them.
SENIORITY_ORDER = (
    "owner", "c_level", "vp", "director", "head",
    "manager", "senior", "staff", "other", "unknown",
)

#: Company-size buckets, in ascending order.
SIZE_BUCKETS = ("1", "2-10", "11-50", "51-200", "201-500", "500+")

#: Revenue bands, in ascending order.
REVENUE_BANDS = ("<1Cr", "1-10Cr", "10-50Cr", "50-100Cr", "100-500Cr", "500Cr+")


def _person_row(contact: Contact, business: Optional[Business]) -> Dict[str, Any]:
    """Flattens a contact and its company into one People-table row."""
    band = contact.seniority or "unknown"
    name = " ".join(
        part for part in (contact.first_name, contact.last_name) if part
    ).strip()
    if not name:
        name = business.name if business else ""
    return {
        "id": contact.id,
        "name": name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "title": contact.title,
        "seniority": band,
        "seniority_label": SENIORITY_LABELS.get(band, band),
        "is_decision_maker": bool(contact.is_decision_maker)
        if contact.is_decision_maker is not None else is_decision_maker(band),
        #: Whether a real human was identified. A row where this is false is
        #: the *business* as an outreach target - it has a phone and a
        #: WhatsApp number, but there is no person behind it yet.
        "is_person": bool(contact.person_identified),
        "contact_kind": "person" if contact.person_identified else "business",
        "email": contact.email,
        "phone": contact.phone,
        "whatsapp_link": contact.whatsapp_link,
        "linkedin_url": contact.linkedin_url,
        "preferred_channel": contact.preferred_channel,
        "is_verified": bool(contact.is_verified),
        "verification_status": contact.verification_status,
        "is_role_account": bool(contact.is_role_account),
        "unsubscribed": bool(contact.unsubscribed),
        "source": contact.source,
        # --- company ---
        "business_id": contact.business_id,
        "business_name": business.name if business else None,
        "business_website": business.website if business else None,
        "business_phone": business.phone if business else None,
        "business_rating": business.rating if business else None,
        "industry": business.industry if business else None,
        "address": business.address if business else None,
        "city": business.city if business else None,
        "state": business.state if business else None,
        "market_tier": business.market_tier if business else None,
        "employee_count": business.employee_count if business else None,
        "size_bucket": business.size_bucket if business else None,
        "revenue": business.revenue if business else None,
        "revenue_band": business.revenue_band if business else None,
        "technologies": (business.technologies or []) if business else [],
        "lead_score": business.score if business else None,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
    }


@router.get("")
@router.get("/")
async def list_people(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    seniority: Optional[str] = Query(
        None,
        description=f"Comma-separated seniority bands. One of: {', '.join(SENIORITY_ORDER)}.",
    ),
    decision_makers_only: bool = Query(
        False, description="Only people who can actually say yes."
    ),
    city: Optional[str] = None,
    state: Optional[str] = None,
    market_tier: Optional[str] = Query(
        None, description="metro / tier_2 / tier_3"
    ),
    industry: Optional[str] = None,
    has_email: Optional[bool] = None,
    verified_only: bool = False,
    size_bucket: Optional[str] = Query(
        None, description=f"Company size. One of: {', '.join(SIZE_BUCKETS)}."
    ),
    min_employees: Optional[int] = Query(None, ge=0),
    max_employees: Optional[int] = Query(None, ge=0),
    revenue_band: Optional[str] = Query(
        None, description=f"One of: {', '.join(REVENUE_BANDS)}."
    ),
    technology: Optional[str] = None,
    sort: str = Query(
        "created",
        pattern="^(created|score|name|seniority|company|employees)$",
    ),
    desc: bool = True,
    include_demo: bool = Query(
        True,
        description="Include the sample rows a fresh database is seeded with.",
    ),
    person_only: bool = Query(
        True,
        description="Only rows where a real human was identified. Set false to "
                    "include business-level outreach targets (a phone and a "
                    "WhatsApp number, but no person behind them yet).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Lists people, one row per human, with company attributes joined in."""
    offset = (page - 1) * limit

    # The People table is a person list: a contact with a business is a
    # person at a company, which is the row a salesperson works with.
    stmt = select(Contact).where(Contact.business_id.isnot(None))
    count_stmt = select(func.count(Contact.id)).where(Contact.business_id.isnot(None))

    if person_only:
        stmt = stmt.where(Contact.person_identified.is_(True))
        count_stmt = count_stmt.where(Contact.person_identified.is_(True))

    if seniority:
        bands = [b.strip().lower() for b in seniority.split(",") if b.strip()]
        valid = [b for b in bands if b in SENIORITY_ORDER]
        if valid:
            stmt = stmt.where(Contact.seniority.in_(valid))
            count_stmt = count_stmt.where(Contact.seniority.in_(valid))

    if decision_makers_only:
        dm = [b for b in DECISION_MAKER_BANDS]
        stmt = stmt.where(Contact.seniority.in_(dm))
        count_stmt = count_stmt.where(Contact.seniority.in_(dm))

    if verified_only:
        stmt = stmt.where(Contact.is_verified.is_(True))
        count_stmt = count_stmt.where(Contact.is_verified.is_(True))

    if has_email is not None:
        if has_email:
            clause = Contact.email.isnot(None) & (Contact.email != "")
        else:
            clause = or_(Contact.email.is_(None), Contact.email == "")
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    # Company-level filters join the business table.
    business_filters = []
    if city:
        business_filters.append(func.lower(Business.city) == city.strip().lower())
    if state:
        business_filters.append(func.lower(Business.state) == state.strip().lower())
    if market_tier:
        business_filters.append(
            func.lower(Business.market_tier) == market_tier.strip().lower()
        )
    if industry:
        business_filters.append(Business.industry.ilike(f"%{industry}%"))
    if size_bucket:
        business_filters.append(Business.size_bucket == size_bucket)
    if min_employees is not None:
        business_filters.append(Business.employee_count >= min_employees)
    if max_employees is not None:
        business_filters.append(Business.employee_count <= max_employees)
    if revenue_band:
        business_filters.append(Business.revenue_band == revenue_band)
    if technology:
        # SQLite JSON: the technologies column is a JSON array, so a LIKE on
        # the serialised text is the portable way to ask "uses Shopify".
        business_filters.append(
            func.cast(Business.technologies, String).ilike(
                f'%"{technology.strip()}"%'
            )
        )
    if not include_demo:
        business_filters.append(
            or_(Business.is_demo == False, Business.is_demo.is_(None))
        )

    if business_filters:
        subquery = select(Business.id).where(*business_filters)
        stmt = stmt.where(Contact.business_id.in_(subquery))
        count_stmt = count_stmt.where(Contact.business_id.in_(subquery))

    if search:
        term = f"%{search.strip()}%"
        name_expr = or_(
            Contact.first_name.ilike(term),
            Contact.last_name.ilike(term),
            Contact.title.ilike(term),
            Contact.email.ilike(term),
            Business.name.ilike(term),
            Business.city.ilike(term),
        )
        stmt = stmt.join(Business, Contact.business_id == Business.id).where(name_expr)
        count_stmt = count_stmt.join(
            Business, Contact.business_id == Business.id
        ).where(name_expr)

    total = (await db.execute(count_stmt)).scalar() or 0

    # Sorting. A person list is useless if it cannot be ordered by the thing
    # you are hunting for.
    sort_map = {
        "created": Contact.created_at,
        "name": Contact.first_name,
        "seniority": Contact.seniority,
        "company": Business.name,
        "employees": Business.employee_count,
        "score": Business.score,
    }
    sort_col = sort_map.get(sort, Contact.created_at)
    if sort == "company" or sort == "employees" or sort == "score":
        stmt = stmt.join(Business, Contact.business_id == Business.id)
    stmt = stmt.order_by(sort_col.desc() if desc else sort_col.asc())
    stmt = stmt.offset(offset).limit(limit)

    rows = (await db.execute(stmt)).unique().scalars().all()

    businesses: Dict[int, Business] = {}
    b_ids = {c.business_id for c in rows if c.business_id}
    if b_ids:
        for b in (await db.execute(
            select(Business).where(Business.id.in_(b_ids))
        )).scalars().all():
            businesses[b.id] = b

    people = [_person_row(c, businesses.get(c.business_id)) for c in rows]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 0,
        "people": people,
    }


@router.get("/facets")
async def people_facets(
    include_demo: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Counts per filter value, so the UI can show what is actually there.

    A filter dropdown with no numbers on it is a guess. These counts are
    what let an operator see "there are 14 owners in Pune" before clicking.
    """
    base_filters = [Contact.business_id.isnot(None), Contact.person_identified.is_(True)]
    if not include_demo:
        base_filters.append(
            or_(Business.is_demo == False, Business.is_demo.is_(None))
        )

    async def _counts(column, limit_n=20):
        """Counts of a business column over the identified-people set.

        The join has to be explicit. Selecting a ``Business`` column while
        counting over a subquery of ``Contact`` made SQLite add
        ``businesses`` to the FROM as a *cross join*, so every city
        reported the total number of people - which is how a dropdown ends
        up promising "13 in Bus Stand Road" for a city that has none.
        """
        rows = (await db.execute(
            select(column, func.count(Contact.id))
            .join(Business, Contact.business_id == Business.id)
            .where(*base_filters)
            .group_by(column)
            .order_by(func.count(Contact.id).desc())
            .limit(limit_n)
        )).all()
        return [
            {"value": value, "count": count}
            for value, count in rows
            if value not in (None, "")
        ]

    seniority_counts = (await db.execute(
        select(Contact.seniority, func.count())
        .join(Business, Contact.business_id == Business.id)
        .where(*base_filters)
        .group_by(Contact.seniority)
    )).all()

    return {
        "seniority": [
            {
                "value": band,
                "label": SENIORITY_LABELS.get(band, band),
                "count": next((c for s, c in seniority_counts if s == band), 0),
            }
            for band in SENIORITY_ORDER
        ],
        "city": await _counts(Business.city, 50),
        "state": await _counts(Business.state, 40),
        "market_tier": await _counts(Business.market_tier, 5),
        "industry": await _counts(Business.industry, 30),
        "size_bucket": await _counts(Business.size_bucket, 10),
        "revenue_band": await _counts(Business.revenue_band, 10),
        "technologies": await _technology_counts(db),
    }


async def _technology_counts(db: AsyncSession) -> List[Dict[str, Any]]:
    """Counts per technology.

    The column is a JSON array, so this reads every row and counts in
    Python. It is a small table - the lead database, not a warehouse - and
    a JSON1 query would be a portability problem for no real gain.
    """
    rows = (await db.execute(
        select(Business.technologies)
        .join(Contact, Contact.business_id == Business.id)
        .where(Contact.person_identified.is_(True))
    )).all()
    counts: Dict[str, int] = {}
    for (techs,) in rows:
        if not isinstance(techs, (list, tuple)):
            continue
        for tech in techs:
            if not tech:
                continue
            counts[tech] = counts.get(tech, 0) + 1
    return [
        {"value": tech, "count": count}
        for tech, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ][:30]


@router.get("/stats")
async def people_stats(
    include_demo: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Headline numbers for the People view.

    ``total_people`` counts only rows where a real human was identified.
    ``business_targets`` counts the rows that are a business with a phone
    but no person behind it yet - which is most of the database, and is
    the honest picture of what the product currently knows.
    """
    filters = [Contact.business_id.isnot(None)]
    if not include_demo:
        filters.append(Contact.business_id.in_(
            select(Business.id).where(
                or_(Business.is_demo == False, Business.is_demo.is_(None))
            )
        ))

    total = (await db.execute(
        select(func.count(Contact.id)).where(*filters)
    )).scalar() or 0
    people = (await db.execute(
        select(func.count(Contact.id)).where(
            *filters, Contact.person_identified.is_(True)
        )
    )).scalar() or 0
    with_email = (await db.execute(
        select(func.count(Contact.id)).where(
            *filters, Contact.email.isnot(None), Contact.email != ""
        )
    )).scalar() or 0
    decision = (await db.execute(
        select(func.count(Contact.id)).where(
            *filters, Contact.seniority.in_(list(DECISION_MAKER_BANDS))
        )
    )).scalar() or 0
    verified = (await db.execute(
        select(func.count(Contact.id)).where(*filters, Contact.is_verified.is_(True))
    )).scalar() or 0
    named = (await db.execute(
        select(func.count(Contact.id)).where(
            *filters, Contact.first_name.isnot(None), Contact.first_name != ""
        )
    )).scalar() or 0

    return {
        "total_people": people,
        "business_targets": max(0, total - people),
        "total_contacts": total,
        "named_people": named,
        "with_email": with_email,
        "verified": verified,
        "decision_makers": decision,
        "coverage": round((people / total) * 100, 1) if total else 0.0,
    }
