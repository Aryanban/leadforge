import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import csv
import io

from app.database import get_db
from app.models.business import Business
from app.models.contact import Contact

router = APIRouter()

class LeadCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = "General"

@router.get("")
@router.get("/")
async def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = None,
    industry: Optional[str] = None,
    has_email: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * limit
    
    # Base query for businesses
    stmt = select(Business)
    
    if search:
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

    # Total count query
    count_stmt = select(func.count(Business.id))
    if search:
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

    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paged query
    stmt = stmt.order_by(Business.created_at.desc()).offset(offset).limit(limit)
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
    for b in businesses:
        b_contacts = contacts_map.get(b.id, [])
        primary_contact = b_contacts[0] if b_contacts else None
        
        # Apply email filter if requested
        if has_email is True and not any(c.get("email") for c in b_contacts):
            continue
        if has_email is False and any(c.get("email") for c in b_contacts):
            continue

        # Compute Google Maps URL
        maps_url = b.maps_url
        if not maps_url:
            extra = b.extra_data or {}
            maps_url = extra.get("maps_url") if isinstance(extra, dict) else None
        if not maps_url and b.place_id and b.place_id.startswith("http"):
            maps_url = b.place_id
        if not maps_url:
            query_str = f"{b.name} {b.address or ''}".strip()
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query_str)}"

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
            "primary_contact": primary_contact,
            "contacts": b_contacts,
            "created_at": b.created_at.isoformat() if b.created_at else None
        })


    return {
        "total": total,
        "page": page,
        "limit": limit,
        "leads": leads_data
    }


@router.get("/export/csv")
async def export_leads_csv(db: AsyncSession = Depends(get_db)):
    """Exports all leads in a clean CSV format for Google Sheets / Excel."""
    stmt = select(Business, Contact).join(Contact, Business.id == Contact.business_id, isouter=True).order_by(Business.id.desc())
    res = await db.execute(stmt)
    rows = res.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Business ID",
        "Business Name",
        "Industry / Category",
        "Phone",
        "Website",
        "Address",
        "Rating",
        "Reviews Count",
        "Contact Name",
        "Contact Email",
        "Email Verified",
        "WhatsApp Link",
        "Google Maps URL"
    ])

    for b, c in rows:
        contact_name = f"{c.first_name or ''} {c.last_name or ''}".strip() if c else ""
        maps_url = b.maps_url or (b.place_id if b.place_id and b.place_id.startswith("http") else f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(b.name + ' ' + (b.address or ''))}")
        writer.writerow([
            b.id,
            b.name or "",
            b.industry or "",
            b.phone or (c.phone if c else "") or "",
            b.website or "",
            b.address or "",
            b.rating or "",
            b.reviews_count or "",
            contact_name,
            c.email if c else "",
            "Yes" if (c and c.is_verified) else "No",
            c.whatsapp_link if c else "",
            maps_url
        ])


    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leadforge_leads_export.csv"}
    )


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
