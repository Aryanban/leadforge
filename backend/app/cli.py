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
from app.database import async_session_maker, ensure_schema
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob
from app.scraper.maps_scraper import scrape_leads_and_save
from app.enricher.email_finder import enrich_business_by_id
from app.campaigns.spam_checker import check_cold_email_spam
from app.enricher.ai_icebreaker import generate_ai_icebreaker


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


async def cmd_scrape(query: str, limit: int = 10, auto_enrich: bool = True, output_format: str = "markdown") -> int:
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
    saved_count, new_biz_ids = await scrape_leads_and_save(query=query, max_results=limit, job_id=job_id)

    # 3. Query the freshly saved/updated leads.
    #
    # Scoped to the businesses THIS scrape created. It used to return the last
    # N businesses in the whole database, so a scrape for "Dentists in Pune"
    # against a database that already held 75 real-estate leads printed 75
    # real-estate agents under a "Dentists in Pune" heading.
    async with async_session_maker() as db:
        if new_biz_ids:
            stmt = select(Business).where(Business.id.in_(new_biz_ids)).order_by(Business.id)
        else:
            stmt = select(Business).where(Business.id.is_(None))
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
    return 0 if leads_data else 1


async def cmd_search(search_term: Optional[str] = None, industry: Optional[str] = None, has_email: Optional[bool] = None, limit: int = 25, output_format: str = "markdown") -> int:
    async with async_session_maker() as db:
        stmt = select(Business)
        if search_term:
            term = f"%{search_term}%"
            stmt = stmt.where(or_(Business.name.ilike(term), Business.address.ilike(term), Business.phone.ilike(term)))
        if industry:
            stmt = stmt.where(Business.industry.ilike(f"%{industry}%"))

        # The "has email" filter is applied in SQL, BEFORE the limit. Filtering
        # after the limit meant the --limit parameter changed the answer:
        # "--limit 5 --has-email" returned 0 matches while "--limit 100" found
        # 6, because the filter ran on an already-truncated set.
        if has_email is not None:
            email_ids = select(Contact.business_id).where(
                Contact.email.isnot(None), Contact.email != ""
            )
            stmt = stmt.where(
                Business.id.in_(email_ids) if has_email
                else Business.id.notin_(email_ids)
            )

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
    return 0 if leads_data else 1


async def cmd_enrich(business_id: int) -> int:
    res = await enrich_business_by_id(business_id)
    print(json.dumps(res, indent=2))
    return 0


async def cmd_stats() -> int:
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
    return 0


async def cmd_spam(subject: str, body: str) -> int:
    res = check_cold_email_spam(subject, body)
    print(json.dumps(res, indent=2))
    # A copy that trips the spam linter is a failure the caller must see.
    return 0 if res.get("is_safe", True) else 1


async def cmd_icebreaker(business_id: int) -> int:
    async with async_session_maker() as db:
        b = await db.get(Business, business_id)
        if not b:
            print(json.dumps({"error": f"Business ID {business_id} not found"}))
            return 1
        c_stmt = select(Contact).where(Contact.business_id == b.id).limit(1)
        c_res = await db.execute(c_stmt)
        c = c_res.scalar_one_or_none()
        first_name = c.first_name if c else ""
        city = b.address.split(",")[-2].strip() if b.address and len(b.address.split(",")) > 1 else (b.address or "your area")
        res = generate_ai_icebreaker(
            business_name=b.name,
            industry=b.industry,
            city=city,
            rating=b.rating,
            reviews_count=b.reviews_count,
            website=b.website,
            first_name=first_name
        )
    print(json.dumps(res, indent=2))
    return 0


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
    p_search.add_argument("--has-email", action="store_true", default=None, help="Only leads with an email address")
    p_search.add_argument("--no-email", action="store_true", default=None, help="Only leads WITHOUT an email address")
    p_search.add_argument("--limit", type=int, default=25, help="Limit")
    p_search.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    # Enrich command
    p_enrich = subparsers.add_parser("enrich", help="Run multi-source web enrichment for a business ID")
    p_enrich.add_argument("business_id", type=int, help="Business ID to enrich")

    # Spam check command
    p_spam = subparsers.add_parser("spam", help="Analyze cold email deliverability and spam risk score")
    p_spam.add_argument("--subject", type=str, required=True, help="Email subject line")
    p_spam.add_argument("--body", type=str, required=True, help="Email body text")

    # Icebreaker command
    p_ice = subparsers.add_parser("icebreaker", help="Generate 1-on-1 personalized AI cold email hooks for a lead")
    p_ice.add_argument("business_id", type=int, help="Business ID to generate hooks for")

    # Stats command
    subparsers.add_parser("stats", help="Get overview statistics")

    args = parser.parse_args()

    # The CLI talks to the database directly, so it must bring the schema up
    # to date itself. It used to rely on the API process having started
    # first, which meant a fresh clone failed with "no such column".
    try:
        asyncio.run(ensure_schema())
    except Exception as schema_err:
        print(json.dumps({"error": f"schema sync failed: {schema_err}"}), file=sys.stderr)
        raise SystemExit(1)

    # Every command returns a process exit code. A CLI that always exits 0
    # cannot be scripted: an agent (or a shell pipeline) has no way to tell
    # "not found" from "found". Errors now exit non-zero and print to stderr.
    exit_code = 0
    try:
        if args.command == "scrape":
            exit_code = asyncio.run(cmd_scrape(query=args.query, limit=args.limit, output_format=args.format))
        elif args.command == "search":
            _has_email = True if args.has_email else (False if args.no_email else None)
            exit_code = asyncio.run(cmd_search(search_term=args.query, industry=args.industry, has_email=_has_email, limit=args.limit, output_format=args.format))
        elif args.command == "enrich":
            exit_code = asyncio.run(cmd_enrich(business_id=args.business_id))
        elif args.command == "spam":
            exit_code = asyncio.run(cmd_spam(subject=args.subject, body=args.body))
        elif args.command == "icebreaker":
            exit_code = asyncio.run(cmd_icebreaker(business_id=args.business_id))
        elif args.command == "stats":
            exit_code = asyncio.run(cmd_stats())
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        raise SystemExit(1)

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
