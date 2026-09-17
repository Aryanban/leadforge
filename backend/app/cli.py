import asyncio
import argparse
import json
import sys
import os
import urllib.parse
from typing import Optional, List, Dict, Any

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, or_, func
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob
from app.scraper.maps_scraper import scrape_leads_and_save
from app.enricher.email_finder import enrich_business_by_id


def format_markdown_table(leads: List[Dict[str, Any]]) -> str:
    if not leads:
        return "No leads found."

    lines = [
        "| Business Name | Google Maps | Phone / WhatsApp | Verified Email | Rating | Address |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]

    for lead in leads:
        name = lead.get("name", "Unknown").replace("|", "\\|")
        maps_url = lead.get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name)}"
        maps_link = f"[View on Maps]({maps_url})"

        phone = lead.get("phone") or "—"
        wa_url = lead.get("whatsapp_link")
        if wa_url:
            phone_cell = f"{phone}<br>[WhatsApp]({wa_url})"
        else:
            phone_cell = phone

        emails = lead.get("emails") or []
        if emails:
            email_parts = []
            for em in emails:
                status = " ✓" if em.get("is_verified") else ""
                email_parts.append(f"`{em.get('email')}`{status}")
            email_cell = "<br>".join(email_parts)
        else:
            email_cell = "*Pending deep search*"

        rating = f"★ {lead.get('rating')}" if lead.get("rating") else "—"
        address = (lead.get("address") or "—").replace("|", "\\|")

        lines.append(f"| **{name}** | {maps_link} | {phone_cell} | {email_cell} | {rating} | {address} |")

    return "\n".join(lines)


async def cmd_scrape(query: str, limit: int = 10, auto_enrich: bool = True, output_format: str = "markdown"):
    """Scrapes leads from Google Maps, saves them, enriches them, and outputs results."""
    # 1. Create scrape job
    job_id = None
    async with async_session_maker() as db:
        job = ScrapeJob(query=query, status="running")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    # 2. Run scraping
    saved_count, _new_biz_ids = await scrape_leads_and_save(query=query, max_results=limit, job_id=job_id)

    # 3. Query the freshly saved/updated leads
    async with async_session_maker() as db:
        stmt = select(Business).order_by(Business.id.desc()).limit(limit)
        res = await db.execute(stmt)
        businesses = res.scalars().all()

        leads_data = []
        for b in businesses:
            c_stmt = select(Contact).where(Contact.business_id == b.id)
            c_res = await db.execute(c_stmt)
            contacts = c_res.scalars().all()

            emails = [
                {"email": c.email, "is_verified": c.is_verified, "status": c.verification_status}
                for c in contacts if c.email
            ]

            clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
            wa_link = f"https://wa.me/{clean_phone}" if clean_phone else None
            maps_url = b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"

            leads_data.append({
                "id": b.id,
                "name": b.name,
                "phone": b.phone,
                "whatsapp_link": wa_link,
                "website": b.website,
                "address": b.address,
                "rating": b.rating,
                "industry": b.industry,
                "maps_url": maps_url,
                "emails": emails
            })

    if output_format == "json":
        print(json.dumps({"query": query, "total": len(leads_data), "leads": leads_data}, indent=2))
    else:
        print(f"### LeadForge Results for: \"{query}\"\n")
        print(f"Discovered **{len(leads_data)}** listings ({saved_count} new leads saved into database).\n")
        print(format_markdown_table(leads_data))


async def cmd_search(search_term: Optional[str] = None, industry: Optional[str] = None, has_email: Optional[bool] = None, limit: int = 25, output_format: str = "markdown"):
    async with async_session_maker() as db:
        stmt = select(Business)
        if search_term:
            term = f"%{search_term}%"
            stmt = stmt.where(or_(Business.name.ilike(term), Business.address.ilike(term), Business.phone.ilike(term)))
        if industry:
            stmt = stmt.where(Business.industry.ilike(f"%{industry}%"))

        stmt = stmt.order_by(Business.id.desc()).limit(limit)
        res = await db.execute(stmt)
        businesses = res.scalars().all()

        leads_data = []
        for b in businesses:
            c_stmt = select(Contact).where(Contact.business_id == b.id)
            c_res = await db.execute(c_stmt)
            contacts = c_res.scalars().all()

            emails = [
                {"email": c.email, "is_verified": c.is_verified, "status": c.verification_status}
                for c in contacts if c.email
            ]

            if has_email is True and not emails:
                continue
            if has_email is False and emails:
                continue

            clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
            wa_link = f"https://wa.me/{clean_phone}" if clean_phone else None
            maps_url = b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"

            leads_data.append({
                "id": b.id,
                "name": b.name,
                "phone": b.phone,
                "whatsapp_link": wa_link,
                "website": b.website,
                "address": b.address,
                "rating": b.rating,
                "industry": b.industry,
                "maps_url": maps_url,
                "emails": emails
            })

    if output_format == "json":
        print(json.dumps({"total": len(leads_data), "leads": leads_data}, indent=2))
    else:
        print(format_markdown_table(leads_data))


async def cmd_enrich(business_id: int):
    res = await enrich_business_by_id(business_id)
    print(json.dumps(res, indent=2))


async def cmd_stats():
    async with async_session_maker() as db:
        res_b = await db.execute(select(func.count(Business.id)))
        total_leads = res_b.scalar() or 0
        res_c = await db.execute(select(func.count(Contact.id)))
        total_contacts = res_c.scalar() or 0
        res_v = await db.execute(select(func.count(Contact.id)).where(Contact.is_verified == True))
        verified_contacts = res_v.scalar() or 0

    print(json.dumps({
        "total_leads": total_leads,
        "total_contacts": total_contacts,
        "verified_contacts": verified_contacts
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="LeadForge AI Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Scrape command
    p_scrape = subparsers.add_parser("scrape", help="Scrape Google Maps leads with real-time web enrichment")
    p_scrape.add_argument("query", type=str, help="Search query (e.g. 'Dentists in Rohini Delhi')")
    p_scrape.add_argument("--limit", type=int, default=10, help="Maximum leads to scrape")
    p_scrape.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # Search command
    p_search = subparsers.add_parser("search", help="Search existing leads in the database")
    p_search.add_argument("--query", type=str, default=None, help="Search term")
    p_search.add_argument("--industry", type=str, default=None, help="Industry filter")
    p_search.add_argument("--has-email", action="store_true", default=None, help="Only leads with email")
    p_search.add_argument("--limit", type=int, default=25, help="Limit")
    p_search.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # Enrich command
    p_enrich = subparsers.add_parser("enrich", help="Run multi-source web enrichment for a business ID")
    p_enrich.add_argument("business_id", type=int, help="Business ID to enrich")

    # Stats command
    subparsers.add_parser("stats", help="Get overview statistics")

    args = parser.parse_args()

    if args.command == "scrape":
        asyncio.run(cmd_scrape(query=args.query, limit=args.limit, output_format=args.format))
    elif args.command == "search":
        asyncio.run(cmd_search(search_term=args.query, industry=args.industry, has_email=args.has_email, limit=args.limit, output_format=args.format))
    elif args.command == "enrich":
        asyncio.run(cmd_enrich(business_id=args.business_id))
    elif args.command == "stats":
        asyncio.run(cmd_stats())


if __name__ == "__main__":
    main()
