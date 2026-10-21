import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete, text
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import csv
import io
import logging

from app.database import get_db
from app.models.business import Business, normalize_phone_e164, canonical_domain_of
from app.models.contact import Contact
from app.models.send import Send
from app.models.campaign import Campaign
from app.models.campaign_step import CampaignStep
from app.campaigns.sender import resolve_city
from app.campaigns.suppression import is_suppressed, add_suppression
from app.enricher.email_finder import calculate_lead_quality_score
from app.enricher.ai_icebreaker import generate_ai_icebreaker
from app.dedupe.match import find_existing_business, normalize_phone, canonical_domain

logger = logging.getLogger(__name__)

router = APIRouter()

class LeadCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = "General"

class TwentyWebhookRequest(BaseModel):
    webhook_url: Optional[str] = None

#: Cached result of "is the FTS index actually there?". Checked once per
#: process: a missing or unavailable index must degrade to the LIKE scan,
#: never to a 500.
_FTS_AVAILABLE: Optional[bool] = None


async def _fts_index_available(db: AsyncSession) -> bool:
    """Whether the FTS5 search index exists and can be queried."""
    global _FTS_AVAILABLE
    if _FTS_AVAILABLE is not None:
        return _FTS_AVAILABLE
    try:
        row = (await db.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='businesses_fts'"
        ))).first()
        _FTS_AVAILABLE = row is not None
    except Exception:
        # Postgres (or any non-SQLite backend) does not use this index.
        _FTS_AVAILABLE = False
    return _FTS_AVAILABLE


async def _fts_search_condition(db: AsyncSession, term: str):
    """A SQLAlchemy condition that matches businesses against the FTS index.

    The match is expressed as a subquery so the candidate ids never have to
    round-trip through Python - a broad search can match 50,000 rows, and
    materialising that as an ``IN (...)`` list is slower than the scan it
    replaced.

    Returns ``None`` when the index cannot answer the query, so the caller
    falls back to the ``LIKE`` scan.
    """
    term = (term or "").strip()
    # The trigram tokenizer needs at least three characters.
    if len(term) < 3:
        return None
    if not await _fts_index_available(db):
        return None

    from app.database import _FTS_TABLE

    # FTS5 query syntax: wrap in double quotes for a literal phrase and
    # double any embedded quote.
    escaped = term.replace('"', '""')
    return (
        text(f"businesses.id IN (SELECT rowid FROM {_FTS_TABLE} WHERE {_FTS_TABLE} MATCH :lf_fts_q)")
        .bindparams(lf_fts_q=f'"{escaped}"')
    )


@router.get("")
@router.get("/")
async def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = None,
    industry: Optional[str] = None,
    has_email: Optional[bool] = None,
    sort: str = Query("created", pattern="^(created|score|name|rating)$"),
    desc: bool = True,
    min_score: Optional[int] = Query(None, ge=0, le=100),
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * limit

    # Base query for businesses
    stmt = select(Business)

    fts_condition = None
    if search:
        fts_condition = await _fts_search_condition(db, search)
        if fts_condition is not None:
            stmt = stmt.where(fts_condition)
    if search and fts_condition is None:
        # Fall back to the LIKE scan.
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Business.name.ilike(search_term),
                Business.address.ilike(search_term),
                Business.phone.ilike(search_term),
                Business.website.ilike(search_term)
            )
        )
    
    if industry:
        stmt = stmt.where(Business.industry.ilike(f"%{industry}%"))

    # The "has email" filter is a SQL predicate, not a Python post-filter.
    #
    # It used to be applied inside the row loop, AFTER the LIMIT/OFFSET had
    # already run, and it was missing from the count query entirely. That
    # meant: `total` always reported the unfiltered count, and the rows that
    # matched the filter were removed from the middle of an already-paged
    # result set. On the Lead Database - the product's front door - a user
    # filtering for "has email" saw 4 rows instead of 20 and could never
    # reach page 2.
    has_email_clause = None
    if has_email is not None:
        email_ids = select(Contact.business_id).where(
            Contact.email.isnot(None), Contact.email != ""
        )
        has_email_clause = (
            Business.id.in_(email_ids) if has_email else Business.id.notin_(email_ids)
        )
        stmt = stmt.where(has_email_clause)

    # Total count query
    count_stmt = select(func.count(Business.id))
    if search:
        if fts_condition is not None:
            # The count reuses the FTS condition, so it is an index lookup
            # instead of a second full-text scan.
            count_stmt = count_stmt.where(fts_condition)
        else:
            search_term = f"%{search}%"
            count_stmt = count_stmt.where(
                or_(
                    Business.name.ilike(search_term),
                    Business.address.ilike(search_term),
                    Business.phone.ilike(search_term),
                    Business.website.ilike(search_term)
                )
            )
    if industry:
        count_stmt = count_stmt.where(Business.industry.ilike(f"%{industry}%"))
    if has_email_clause is not None:
        count_stmt = count_stmt.where(has_email_clause)
    if min_score is not None:
        stmt = stmt.where(Business.score >= min_score)
        count_stmt = count_stmt.where(Business.score >= min_score)
    if source:
        stmt = stmt.where(Business.source == source)
        count_stmt = count_stmt.where(Business.source == source)

    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paged query. Sorting is parameterised (the old hard-coded
    # `created_at desc` meant "show me the hottest leads" was impossible
    # without a code change).
    _sort_columns = {
        "created": Business.created_at,
        "score": Business.score,
        "name": Business.name,
        "rating": Business.rating,
    }
    _sort_col = _sort_columns.get(sort, Business.created_at)
    stmt = stmt.order_by(_sort_col.desc() if desc else _sort_col.asc())
    stmt = stmt.offset(offset).limit(limit)
    res = await db.execute(stmt)
    businesses = res.scalars().all()

    # Load contacts for these businesses
    b_ids = [b.id for b in businesses]
    contacts_map: Dict[int, List[Dict[str, Any]]] = {b_id: [] for b_id in b_ids}
    if b_ids:
        c_stmt = select(Contact).where(Contact.business_id.in_(b_ids))
        c_res = await db.execute(c_stmt)
        for c in c_res.scalars().all():
            contacts_map[c.business_id].append({
                "id": c.id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "phone": c.phone,
                "whatsapp_link": c.whatsapp_link,
                "social_links": c.social_links,
                "is_verified": c.is_verified,
                "verification_status": c.verification_status,
                "unsubscribed": c.unsubscribed
            })

    leads_data = []
    #: Business ids whose persisted score was stale and has just been
    #: recomputed.
    stale_score_ids: List[int] = []
    for b in businesses:
        b_contacts = contacts_map.get(b.id, [])
        primary_contact = b_contacts[0] if b_contacts else None

        # Compute Google Maps URL
        extra = b.extra_data if isinstance(b.extra_data, dict) else {}
        maps_url = b.maps_url
        if not maps_url:
            maps_url = extra.get("maps_url") if isinstance(extra, dict) else None
        if not maps_url and b.place_id and b.place_id.startswith("http"):
            maps_url = b.place_id
        if not maps_url:
            query_str = f"{b.name} {b.address or ''}".strip()
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query_str)}"

        # Scrape and Apollo Enrichment attributes
        is_claimed = extra.get("is_claimed", True)
        operational_status = extra.get("operational_status", "Operational")
        price_tier = extra.get("price_tier")

        # The lead score is computed LIVE, never read from the enrichment-time
        # cache.
        #
        # The cache stored an ICP-relative score computed with whatever ICP
        # was attached when the lead was enriched. Changing the ICP weights or
        # switching preset therefore had *no* effect on the Lead Database - the
        # stale cached value won, and scores from different ICPs were not
        # comparable. Computing it live makes the score mean the same thing
        # everywhere and makes ICP tuning visible immediately.
        score_info = calculate_lead_quality_score(b, b_contacts)
        lead_score = score_info["score"]
        lead_tier = score_info["tier"]
        lead_badges = score_info["badges"]
        # Keep the column in sync so it can be sorted/filterable in SQL. Only
        # when it actually changed: this endpoint is a GET, and taking the
        # database's write lock on every page view is pure overhead.
        if b.score != lead_score:
            b.score = lead_score
            stale_score_ids.append(b.id)

        # India source-trust: surfaces *why* a lead's score was adjusted —
        # self-listed directories (JustDial/IndiaMART) carry shared/stale
        # risk, live GBP and first-party sites do not. Advisory for the UI.
        #
        # The modifier reported here must be the one that was ACTUALLY
        # applied to the score. Recomputing it independently meant the API
        # advertised a trust bonus that the scorer had never applied (the
        # primary scrape path's source values were missing from the trust
        # table entirely), so the dashboard showed a badge next to a number
        # that did not include it.
        from app.qualifier.source_trust import source_trust, trust_score_modifier
        _trust_val, _trust_note = source_trust(getattr(b, "source", None))
        _applied_modifier = score_info.get("trust_modifier") if score_info else None
        if _applied_modifier is None:
            _applied_modifier = trust_score_modifier(_trust_val)

        leads_data.append({
            "id": b.id,
            "name": b.name,
            "website": b.website,
            "phone": b.phone,
            "address": b.address,
            "maps_url": maps_url,
            "rating": b.rating,
            "reviews_count": b.reviews_count,
            "industry": b.industry,
            "latitude": b.latitude,
            "longitude": b.longitude,
            "is_claimed": is_claimed,
            "operational_status": operational_status,
            "price_tier": price_tier,
            "lead_score": lead_score,
            "lead_tier": lead_tier,
            "lead_badges": lead_badges,
            "source": getattr(b, "source", None),
            "source_trust": _trust_val,
            "trust_note": _trust_note,
            "trust_modifier": _applied_modifier,
            "primary_contact": primary_contact,
            "contacts": b_contacts,
            "created_at": b.created_at.isoformat() if b.created_at else None
        })

    # Persist the refreshed scores so they are sortable/filterable in SQL.
    # A read that has nothing to write must not take the write lock.
    if stale_score_ids:
        await db.commit()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "leads": leads_data
    }


@router.get("/export/csv")
async def export_leads_csv():
    """Exports all leads in a clean CSV format for Google Sheets / Excel.

    The export is STREAMED. It used to materialise every row into memory and
    build the whole CSV string before responding: 1.4 MB for 5,000 leads,
    ~125 MB for 500,000, and multi-GB beyond that - and it held the request
    open for the whole time. Now the rows are fetched with a server-side
    cursor and written out in 64 KB chunks, so the memory cost is constant
    regardless of database size and the first bytes reach the client
    immediately.
    """
    header = [
        "Business ID",
        "Business Name",
        "Industry / Category",
        "Phone",
        "Website",
        "Address",
        "Rating",
        "Reviews Count",
        "Lead Score",
        "Lead Tier",
        "Claimed GBP",
        "Latitude",
        "Longitude",
        "Contact Name",
        "Contact Email",
        "Email Verified",
        "WhatsApp Link",
        "Google Maps URL"
    ]

    async def _generate():
        # A dedicated session: the request's own session is closed as soon
        # as the endpoint returns, which would be before the stream is
        # consumed.
        from app.database import async_session_maker

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        stmt = (
            select(Business, Contact)
            .join(Contact, Business.id == Contact.business_id, isouter=True)
            .order_by(Business.id.desc())
        )

        async with async_session_maker() as sdb:
            result = await sdb.stream(stmt)
            async for b, c in result:
                contact_name = (
                    f"{c.first_name or ''} {c.last_name or ''}".strip() if c else ""
                )
                maps_url = b.maps_url or (
                    b.place_id if b.place_id and b.place_id.startswith("http")
                    else "https://www.google.com/maps/search/?api=1&query="
                         f"{urllib.parse.quote((b.name or '') + ' ' + (b.address or ''))}"
                )
                extra = b.extra_data if isinstance(b.extra_data, dict) else {}
                is_claimed = extra.get("is_claimed", True)
                lead_score = extra.get("lead_score")
                lead_tier = extra.get("lead_tier")
                if lead_score is None:
                    score_info = calculate_lead_quality_score(b, [c] if c else [])
                    lead_score = score_info["score"]
                    lead_tier = score_info["tier"]

                writer.writerow([
                    b.id,
                    b.name or "",
                    b.industry or "",
                    b.phone or (c.phone if c else "") or "",
                    b.website or "",
                    b.address or "",
                    b.rating or "",
                    b.reviews_count or "",
                    lead_score,
                    lead_tier,
                    "Yes" if is_claimed else "No (Unclaimed)",
                    b.latitude or "",
                    b.longitude or "",
                    contact_name,
                    c.email if c else "",
                    "Yes" if (c and c.is_verified) else "No",
                    c.whatsapp_link if c else "",
                    maps_url,
                ])

                if buffer.tell() > 65536:
                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate(0)

        if buffer.tell():
            yield buffer.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leadforge_leads.csv"},
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leadforge_leads_export.csv"}
    )


@router.get("/export/twenty-crm")
@router.post("/export/twenty-crm")
async def export_leads_twenty_crm(payload: Optional[TwentyWebhookRequest] = None, db: AsyncSession = Depends(get_db)):
    """
    Exports leads in Twenty CRM / Open-Source CRM standard JSON format.
    If webhook_url is provided, automatically posts the batch payload to the target endpoint.
    """
    stmt = select(Business).order_by(Business.id.desc())
    res = await db.execute(stmt)
    businesses = res.scalars().all()

    b_ids = [b.id for b in businesses]
    contacts_map: Dict[int, List[Contact]] = {b_id: [] for b_id in b_ids}
    if b_ids:
        c_stmt = select(Contact).where(Contact.business_id.in_(b_ids))
        c_res = await db.execute(c_stmt)
        for c in c_res.scalars().all():
            contacts_map[c.business_id].append(c)

    companies = []
    for b in businesses:
        b_contacts = contacts_map.get(b.id, [])
        extra = b.extra_data if isinstance(b.extra_data, dict) else {}
        is_claimed = extra.get("is_claimed", True)
        
        score_info = calculate_lead_quality_score(b, b_contacts)
        lead_score = extra.get("lead_score", score_info["score"])
        lead_tier = extra.get("lead_tier", score_info["tier"])

        people = []
        for c in b_contacts:
            people.append({
                "firstName": c.first_name,
                "lastName": c.last_name,
                "jobTitle": c.title or "Owner / Decision Maker",
                "emails": {
                    "primaryEmail": c.email,
                    "additionalEmails": []
                },
                "phones": {
                    "primaryPhone": c.phone or b.phone,
                    "additionalPhones": []
                },
                "whatsappUrl": c.whatsapp_link,
                "isEmailVerified": c.is_verified,
                "verificationStatus": c.verification_status
            })

        domain = ""
        if b.website:
            try:
                parsed = urllib.parse.urlparse(b.website if b.website.startswith("http") else f"https://{b.website}")
                domain = parsed.netloc.replace("www.", "")
            except Exception:
                domain = b.website

        companies.append({
            "name": b.name,
            "domainName": domain,
            "address": {
                "addressStreet1": b.address or "",
                "addressCity": "",
                "addressPostcode": "",
                "addressCountry": ""
            },
            "rating": b.rating,
            "reviewsCount": b.reviews_count,
            "leadScore": lead_score,
            "leadTier": lead_tier,
            "isClaimedGBP": is_claimed,
            "coordinates": {
                "lat": b.latitude,
                "lng": b.longitude
            },
            "people": people
        })

    export_payload = {
        "version": "1.0",
        "source": "leadforge",
        "total_records": len(companies),
        "companies": companies
    }

    if payload and payload.webhook_url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(payload.webhook_url, json=export_payload)
                return {
                    "status": "synced",
                    "webhook_url": payload.webhook_url,
                    "status_code": resp.status_code,
                    "synced_companies": len(companies)
                }
        except Exception as hook_err:
            raise HTTPException(status_code=500, detail=f"Webhook delivery failed: {hook_err}")

    return export_payload


@router.post("/")
async def create_lead(lead: LeadCreate, db: AsyncSession = Depends(get_db)):
    business = Business(
        name=lead.name,
        phone=lead.phone,
        website=lead.website,
        address=lead.address,
        industry=lead.industry
    )
    db.add(business)
    await db.flush()

    if lead.email or lead.phone:
        contact = Contact(
            business_id=business.id,
            first_name=lead.name.split()[0] if lead.name else "Contact",
            email=lead.email,
            phone=lead.phone,
            whatsapp_link=f"https://wa.me/{''.join(filter(str.isdigit, lead.phone))}" if lead.phone else None,
            is_verified=False,
            source="manual"
        )
        db.add(contact)

    await db.commit()
    return {"id": business.id, "name": business.name, "status": "created"}


@router.delete("/{business_id}")
async def delete_lead(business_id: int, db: AsyncSession = Depends(get_db)):
    stmt = delete(Business).where(Business.id == business_id)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted", "id": business_id}


from fastapi import Request


class _BusinessIndex:
    """In-memory lookup tables for bulk dedupe.

    One scan of the businesses (and their contact phones) replaces five
    SELECTs per imported row.
    """

    __slots__ = ("by_place_id", "by_phone", "by_domain", "by_name")

    def __init__(self) -> None:
        self.by_place_id: Dict[str, int] = {}
        self.by_phone: Dict[str, int] = {}
        self.by_domain: Dict[str, int] = {}
        self.by_name: Dict[str, int] = {}

    def add(self, business_id: int, place_id=None, phone=None, website=None, name=None) -> None:
        if place_id:
            self.by_place_id.setdefault(place_id, business_id)
        normalised = normalize_phone(phone)
        if normalised:
            self.by_phone.setdefault(normalised, business_id)
        domain = canonical_domain(website)
        if domain:
            self.by_domain.setdefault(domain, business_id)
        if name:
            self.by_name.setdefault(name, business_id)


async def _build_business_index(db: AsyncSession) -> _BusinessIndex:
    """Builds the dedupe lookup tables from a single scan.

    Only the columns the matcher needs are selected, and they are selected
    as plain tuples - loading 500k full ORM entities would flood the
    session's identity map for no benefit.
    """
    index = _BusinessIndex()

    rows = (await db.execute(
        select(
            Business.id,
            Business.place_id,
            Business.phone,
            Business.phone_e164,
            Business.domain,
            Business.website,
            Business.name,
        )
    )).all()

    for bid, place_id, phone, phone_e164, domain, website, name in rows:
        index.by_name.setdefault(name, bid) if name else None
        if place_id:
            index.by_place_id.setdefault(place_id, bid)
        if phone_e164:
            index.by_phone.setdefault(phone_e164, bid)
        else:
            normalised = normalize_phone(phone)
            if normalised:
                index.by_phone.setdefault(normalised, bid)
        if domain:
            index.by_domain.setdefault(domain, bid)
        else:
            canonical = canonical_domain(website)
            if canonical:
                index.by_domain.setdefault(canonical, bid)

    # A contact's phone identifies the business it belongs to.
    contact_rows = (await db.execute(
        select(Contact.phone, Contact.business_id).where(Contact.phone.isnot(None))
    )).all()
    for phone, business_id in contact_rows:
        normalised = normalize_phone(phone)
        if normalised and business_id:
            index.by_phone.setdefault(normalised, business_id)

    return index


async def _flush_import_chunk(db: AsyncSession, chunk: List[dict],
                              index: _BusinessIndex) -> None:
    """Persists one chunk of CSV rows and keeps the index up to date.

    New rows are inserted in bulk - one ``INSERT ... RETURNING id`` for the
    whole chunk of businesses and one for the contacts - rather than a
    flush per row. A per-row flush is one driver round-trip each, which was
    the remaining ~1ms/row after the dedupe queries were removed.
    """
    new_rows: List[dict] = []
    existing_rows: List[dict] = []
    for item in chunk:
        (existing_rows if item["business"] is not None else new_rows).append(item)

    # --- bulk insert the new businesses -----------------------------------
    if new_rows:
        payloads: List[dict] = []
        contact_payloads: List[dict] = []

        for item in new_rows:
            lead = item["lead"]
            raw_phone = item["phone"]
            raw_email = item["email"]
            raw_name = lead["name"]

            digits_only = "".join(filter(str.isdigit, raw_phone or ""))
            wa_link = f"https://wa.me/{digits_only}" if digits_only else None

            # Score from plain values: the scorer reads attributes through a
            # helper that also accepts dicts, so a row does not have to be
            # flushed before it can be scored.
            score_info = calculate_lead_quality_score(
                {
                    "name": raw_name,
                    "phone": raw_phone,
                    "website": lead.get("website"),
                    "address": lead.get("address"),
                    "industry": item["industry"],
                    "rating": None,
                    "reviews_count": None,
                    "source": None,
                },
                [{
                    "email": raw_email,
                    "is_verified": False,
                    "whatsapp_link": wa_link,
                }],
            )

            payloads.append({
                "name": raw_name,
                "phone": raw_phone,
                "website": lead.get("website"),
                "address": lead.get("address"),
                "industry": item["industry"],
                # Derived identity columns - a Core insert bypasses the ORM's
                # before_insert listener, so they are set explicitly here.
                "phone_e164": normalize_phone_e164(raw_phone),
                "domain": canonical_domain_of(lead.get("website")),
                "extra_data": {
                    "lead_score": score_info["score"],
                    "lead_tier": score_info["tier"],
                    "lead_badges": score_info["badges"],
                    "imported_via": "csv",
                },
                "score": score_info["score"],
            })

            item["_contact"] = {
                "first_name": raw_name.split()[0] if raw_name else "Contact",
                "email": raw_email,
                "phone": raw_phone,
                "whatsapp_link": wa_link,
                "is_verified": False,
                "verification_status": "pending",
                "is_role_account": False,
                "is_free_email": False,
                "unsubscribed": False,
                "source": "csv_import",
            }

        result = await db.execute(
            Business.__table__.insert().returning(Business.__table__.c.id),
            payloads,
        )
        new_ids = list(result.scalars().all())

        for item, business_id in zip(new_rows, new_ids):
            item["business_id"] = business_id
            index.add(business_id, place_id=item["lead"].get("place_id"),
                      phone=item["phone"], website=item["lead"].get("website"),
                      name=item["lead"]["name"])
            contact = dict(item["_contact"])
            contact["business_id"] = business_id
            contact_payloads.append(contact)

        if contact_payloads:
            await db.execute(Contact.__table__.insert(), contact_payloads)

    # --- update the rows that matched an existing business ----------------
    if existing_rows:
        # One query for the whole chunk's contacts, instead of one per row.
        business_ids = [item["business_id"] for item in existing_rows]
        contacts_by_business: Dict[int, List[Contact]] = {}
        if business_ids:
            rows_c = (await db.execute(
                select(Contact).where(Contact.business_id.in_(business_ids))
            )).scalars().all()
            for contact in rows_c:
                contacts_by_business.setdefault(contact.business_id, []).append(contact)

    for item in existing_rows:
        business = item["business"]
        business_id = item["business_id"]
        raw_email = item["email"]
        raw_phone = item["phone"]
        raw_name = item["lead"]["name"]

        contact_list = []
        if raw_email or raw_phone:
            existing_contact = None
            if raw_email:
                existing_contact = next(
                    (c for c in contacts_by_business.get(business_id, [])
                     if c.email == raw_email),
                    None,
                )

            if existing_contact is not None:
                if raw_phone and not existing_contact.phone:
                    existing_contact.phone = raw_phone
                contact_list.append(existing_contact)
            else:
                digits_only = "".join(filter(str.isdigit, raw_phone or ""))
                wa_link = f"https://wa.me/{digits_only}" if digits_only else None
                contact = Contact(
                    business_id=business_id,
                    first_name=raw_name.split()[0] if raw_name else "Contact",
                    email=raw_email,
                    phone=raw_phone,
                    whatsapp_link=wa_link,
                    is_verified=False,
                    source="csv_import"
                )
                db.add(contact)
                contact_list.append(contact)
                contacts_by_business.setdefault(business_id, []).append(contact)

        score_info = calculate_lead_quality_score(business, contact_list)
        business.extra_data = {
            "lead_score": score_info["score"],
            "lead_tier": score_info["tier"],
            "lead_badges": score_info["badges"],
            "imported_via": "csv"
        }
        business.score = score_info["score"]


@router.post("/import/csv")
async def import_leads_csv(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Apollo/Clay-grade Bulk Lead CSV Importer.
    Accepts CSV file upload, JSON payload with csv_content, or raw text CSV.
    Automatically assigns lead quality scores and WhatsApp links.
    """
    content_type = request.headers.get("content-type", "")
    csv_text = ""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload and hasattr(upload, "read"):
            content = await upload.read()
            csv_text = content.decode("utf-8", errors="ignore")
        elif "csv_content" in form:
            csv_text = str(form["csv_content"])
        else:
            raise HTTPException(status_code=400, detail="No file or csv_content found in multipart request")
    elif "application/json" in content_type:
        body = await request.json()
        csv_text = body.get("csv_content", "")
    else:
        raw = await request.body()
        csv_text = raw.decode("utf-8", errors="ignore")

    if not csv_text.strip():
        raise HTTPException(status_code=400, detail="CSV content is empty")

    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must contain a header row")

    fieldnames = [fn.strip() for fn in reader.fieldnames]

    def match_header(candidates: List[str]) -> Optional[str]:
        for fn in fieldnames:
            normalized = fn.lower().replace(" ", "_").replace("-", "_")
            if normalized in candidates:
                return fn
        return None

    name_col = match_header(["business_name", "company_name", "company", "name", "business", "title"]) or fieldnames[0]
    email_col = match_header(["email", "contact_email", "e_mail", "mail", "primary_email"])
    phone_col = match_header(["phone", "phone_number", "mobile", "tel", "telephone", "contact_number"])
    website_col = match_header(["website", "domain", "url", "web_url", "web"])
    address_col = match_header(["address", "location", "city", "street", "full_address"])
    industry_col = match_header(["industry", "category", "niche", "sector"])

    imported = 0
    skipped = 0
    updated = 0

    # --- Bulk dedupe index -------------------------------------------------
    #
    # The importer used to run ~5 SELECTs per row (place_id, phone on the
    # business, phone on the contacts, domain, name, plus a contact lookup)
    # - roughly 25,000 round-trips for a 5,000-row CSV, which is why a
    # 5,000-row import took ~12 seconds and held the database's write lock
    # for the whole thing.
    #
    # The same lookups are now built ONCE, from a single scan, and matched
    # in Python. The scan selects plain tuples rather than ORM entities, so
    # a 500k-row database does not flood the session's identity map.
    index = await _build_business_index(db)

    def _match(lead: dict) -> Optional[int]:
        """Business id of an existing match, in the same priority order as
        ``find_existing_business``."""
        pid = lead.get("place_id")
        if pid and pid in index.by_place_id:
            return index.by_place_id[pid]
        phone = normalize_phone(lead.get("phone"))
        if phone and phone in index.by_phone:
            return index.by_phone[phone]
        domain = canonical_domain(lead.get("website"))
        if domain and domain in index.by_domain:
            return index.by_domain[domain]
        name = lead.get("name")
        if name and name in index.by_name:
            return index.by_name[name]
        return None

    # Rows are processed in chunks so the transaction (and SQLite's write
    # lock) is released periodically instead of being held for the whole file.
    CHUNK_SIZE = 500
    pending: List[dict] = []

    for row in reader:
        raw_name = (row.get(name_col) or "").strip()
        if not raw_name:
            skipped += 1
            continue

        raw_phone = (row.get(phone_col) or "").strip() if phone_col else None
        raw_email = (row.get(email_col) or "").strip() if email_col else None
        raw_website = (row.get(website_col) or "").strip() if website_col else None
        raw_address = (row.get(address_col) or "").strip() if address_col else None
        raw_industry = (row.get(industry_col) or "").strip() if industry_col else "General"

        lead = {
            "name": raw_name,
            "phone": raw_phone,
            "email": raw_email,
            "website": raw_website,
            "address": raw_address,
            "place_id": None,
        }
        matched_id = _match(lead)

        if matched_id is not None:
            # Fill in any blanks on the existing record (idempotent re-import).
            existing = await db.get(Business, matched_id)
            if existing is not None:
                if raw_phone and not existing.phone:
                    existing.phone = raw_phone
                if raw_website and not existing.website:
                    existing.website = raw_website
                if raw_address and not existing.address:
                    existing.address = raw_address
                if raw_industry and (not existing.industry or existing.industry == "General"):
                    existing.industry = raw_industry
                business = existing
                business_id = existing.id
                updated += 1
            else:
                business = None
                business_id = None
        else:
            business = None
            business_id = None
            imported += 1

        pending.append({
            "business": business,
            "business_id": business_id,
            "lead": lead,
            "email": raw_email,
            "phone": raw_phone,
            "industry": raw_industry,
        })

        if len(pending) >= CHUNK_SIZE:
            await _flush_import_chunk(db, pending, index)
            pending = []

    if pending:
        await _flush_import_chunk(db, pending, index)

    await db.commit()
    return {
        "status": "success",
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "total_rows_processed": imported + updated + skipped
    }


@router.get("/{business_id}/icebreaker")
@router.post("/{business_id}/icebreaker")
async def get_lead_icebreaker(business_id: int, db: AsyncSession = Depends(get_db)):
    """Generates personalized AI cold outreach icebreakers for a specific lead."""
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Lead not found")

    c_stmt = select(Contact).where(Contact.business_id == business_id).limit(1)
    c_res = await db.execute(c_stmt)
    contact = c_res.scalars().first()

    icebreaker = generate_ai_icebreaker(
        business_name=business.name,
        industry=business.industry,
        city=resolve_city(business),
        rating=business.rating,
        reviews_count=business.reviews_count,
        website=business.website,
        first_name=contact.first_name if contact else None
    )

    return {
        "business_id": business.id,
        "business_name": business.name,
        **icebreaker
    }

@router.get("/{business_id}/detail")
async def get_lead_detail(business_id: int, db: AsyncSession = Depends(get_db)):
    """Everything the Lead Database side-drawer needs in one round-trip.

    Business + full contacts (verification detail, suppression state) + the
    send timeline across every campaign that ever touched it.
    """
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Lead not found")

    contacts = (await db.execute(
        select(Contact).where(Contact.business_id == business_id)
    )).scalars().all()
    c_ids = [c.id for c in contacts]

    contact_out = []
    for c in contacts:
        suppressed = await is_suppressed(db, c.email) if c.email else None
        contact_out.append({
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
            "verification_sub_status": c.verification_sub_status,
            "verification_confidence": c.verification_confidence,
            "verification_detail": c.verification_detail,
            "is_role_account": bool(c.is_role_account),
            "is_free_email": bool(c.is_free_email),
            "unsubscribed": bool(c.unsubscribed),
            "suppressed": suppressed,
            "source": c.source,
        })

    timeline = []
    if c_ids:
        rows = (await db.execute(
            select(Send, Campaign, CampaignStep)
            .outerjoin(Campaign, Campaign.id == Send.campaign_id)
            .outerjoin(CampaignStep, CampaignStep.id == Send.step_id)
            .where(Send.contact_id.in_(c_ids))
            .order_by(Send.created_at.desc()).limit(100)
        )).all()
        for s, camp, step in rows:
            contact = next((cc for cc in contacts if cc.id == s.contact_id), None)
            timeline.append({
                "send_id": s.id,
                "campaign_id": s.campaign_id,
                "campaign_name": camp.name if camp else None,
                "step_subject": step.subject if step else None,
                "status": s.status,
                "opened": bool(s.opened),
                "replied": bool(s.replied),
                "reply_category": s.reply_category,
                "variant_used": getattr(s, "variant_used", None),
                "error_message": s.error_message,
                "sent_at": s.sent_at.isoformat() if s.sent_at else None,
                "contact_email": contact.email if contact else None,
            })

    maps_url = business.maps_url or (
        f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((business.name + ' ' + (business.address or '')).strip())}"
    )
    return {
        "business": {
            "id": business.id,
            "name": business.name,
            "industry": business.industry,
            "phone": business.phone,
            "website": business.website,
            "address": business.address,
            "rating": business.rating,
            "reviews_count": business.reviews_count,
            "maps_url": maps_url,
        },
        "contacts": contact_out,
        "timeline": timeline,
    }


@router.post("/{business_id}/suppress")
async def suppress_lead(business_id: int, db: AsyncSession = Depends(get_db)):
    """Company-level do-not-contact: suppresses every email on this lead.

    A "do not contact this company" request is per-company, not per-person —
    so this loops all contacts, matching the poller's opt_out behaviour.
    """
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Lead not found")
    contacts = (await db.execute(
        select(Contact).where(Contact.business_id == business_id)
    )).scalars().all()
    added = 0
    for c in contacts:
        if not c.email:
            continue
        if await add_suppression(db, c.email, "manual",
                                 detail=f"suppressed via lead #{business_id}"):
            added += 1
        c.unsubscribed = True
    await db.commit()
    return {"business_id": business_id, "suppressed": added}

