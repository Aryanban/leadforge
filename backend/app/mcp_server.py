#!/usr/bin/env python3
"""
LeadForge Model Context Protocol (MCP) Server
Enables AI assistants (Antigravity, Claude Desktop, Cursor, etc.) to natively:
1. Scrape Google Maps leads in real-time
2. Discover missing emails & phones via multi-source web search
3. Search and filter the local lead database
4. Launch cold email outreach sequences
"""

import sys
import os
import json
import asyncio
import logging
import urllib.parse
from typing import Dict, Any, List, Optional

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, or_, func
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob
from app.models.campaign import Campaign
from app.models.campaign_step import CampaignStep
from app.scraper.maps_scraper import scrape_leads_and_save
from app.enricher.email_finder import enrich_business_by_id

# Configure logging to stderr so stdout remains clean for JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadforge-mcp")


TOOLS_DEFINITIONS = [
    {
        "name": "leadforge_scrape",
        "description": "Scrapes business listings from Google Maps in real-time, extracts phone numbers, ratings, addresses, and official websites, automatically discovers emails from across the open web, and saves them to the database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Target search query and location (e.g. 'Real Estate Agents in Rohini Sector 11 Delhi' or 'Dentists in Austin TX')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of leads to extract (default: 10, max: 50)",
                    "default": 10
                },
                "auto_enrich": {
                    "type": "boolean",
                    "description": "Whether to automatically search the web (Yahoo/Bing/directories/websites) to discover missing emails and phone numbers (default: true)",
                    "default": True
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "leadforge_search_leads",
        "description": "Searches and filters existing businesses in the LeadForge database with contact emails, phones, and hyperlinked Google Maps listings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search keyword matching business name, address, or phone"
                },
                "industry": {
                    "type": "string",
                    "description": "Filter by business category or industry"
                },
                "has_email": {
                    "type": "boolean",
                    "description": "Filter only leads that have discovered email addresses"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of leads to retrieve (default: 15)",
                    "default": 15
                }
            }
        }
    },
    {
        "name": "leadforge_enrich_lead",
        "description": "Runs multi-source web enrichment (Yahoo/Bing search, directory extraction, website crawling, and DNS/SMTP verification) on a business to find emails, phone numbers, and WhatsApp links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "business_id": {
                    "type": "integer",
                    "description": "The numeric ID of the business to enrich"
                }
            },
            "required": ["business_id"]
        }
    },
    {
        "name": "leadforge_create_campaign",
        "description": "Creates a cold email outreach sequence with automated step delays and variable personalization ({{business_name}}, {{first_name}}, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Campaign name"
                },
                "steps": {
                    "type": "array",
                    "description": "List of sequence steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string", "description": "Email subject line"},
                            "body_text": {"type": "string", "description": "Plain text email body"},
                            "body_html": {"type": "string", "description": "Optional HTML formatted email body"},
                            "delay_days": {"type": "integer", "description": "Days to wait before sending this step"}
                        },
                        "required": ["subject", "body_text"]
                    }
                }
            },
            "required": ["name", "steps"]
        }
    },
    {
        "name": "leadforge_get_stats",
        "description": "Gets an analytics overview of total leads, verified contacts, active campaigns, and recent scraping jobs.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Executes an MCP tool and returns markdown-formatted response for the AI assistant."""

    if name == "leadforge_scrape":
        query = arguments.get("query")
        max_results = min(int(arguments.get("max_results", 10)), 50)
        auto_enrich = arguments.get("auto_enrich", True)

        # Create scrape job record
        job_id = None
        async with async_session_maker() as db:
            job = ScrapeJob(query=query, status="running")
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        # Run scrape
        saved_count, _new_biz_ids = await scrape_leads_and_save(query=query, max_results=max_results, job_id=job_id)

        # Fetch newly scraped leads
        async with async_session_maker() as db:
            stmt = select(Business).order_by(Business.id.desc()).limit(max_results)
            res = await db.execute(stmt)
            businesses = res.scalars().all()

            results = []
            for b in businesses:
                c_stmt = select(Contact).where(Contact.business_id == b.id)
                c_res = await db.execute(c_stmt)
                contacts = c_res.scalars().all()

                emails = [
                    f"`{c.email}`" + (" (✓ deliverable)" if c.is_verified else "")
                    for c in contacts if c.email
                ]

                clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
                wa_link = f"[WhatsApp](https://wa.me/{clean_phone})" if clean_phone else ""
                maps_url = b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"

                results.append({
                    "id": b.id,
                    "name": b.name,
                    "maps_url": maps_url,
                    "phone": b.phone or "—",
                    "whatsapp": wa_link or "—",
                    "website": b.website or "—",
                    "emails": "<br>".join(emails) if emails else "*None*",
                    "rating": f"★ {b.rating}" if b.rating else "—",
                    "address": b.address or "—"
                })

        # Format markdown response
        md = [
            f"### LeadForge Google Maps Scrape Results for: \"{query}\"\n",
            f"• **Leads Extracted**: {len(results)}",
            f"• **New Leads Saved**: {saved_count}\n",
            "| Business Name | Google Maps | Phone | WhatsApp | Website | Verified Emails | Rating |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for r in results:
            name_clean = r["name"].replace("|", "\\|")
            maps_link = f"[View Listing]({r['maps_url']})"
            web_link = f"[Website]({r['website']})" if r['website'] != "—" else "—"
            md.append(f"| **{name_clean}** | {maps_link} | {r['phone']} | {r['whatsapp']} | {web_link} | {r['emails']} | {r['rating']} |")

        return "\n".join(md)

    elif name == "leadforge_search_leads":
        search_term = arguments.get("search")
        industry = arguments.get("industry")
        has_email = arguments.get("has_email")
        limit = min(int(arguments.get("limit", 15)), 100)

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

            results = []
            for b in businesses:
                c_stmt = select(Contact).where(Contact.business_id == b.id)
                c_res = await db.execute(c_stmt)
                contacts = c_res.scalars().all()

                emails = [
                    f"`{c.email}`" + (" (✓ verified)" if c.is_verified else "")
                    for c in contacts if c.email
                ]

                if has_email is True and not emails:
                    continue
                if has_email is False and emails:
                    continue

                clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
                wa_link = f"[WhatsApp](https://wa.me/{clean_phone})" if clean_phone else ""
                maps_url = b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"

                results.append({
                    "id": b.id,
                    "name": b.name,
                    "maps_url": maps_url,
                    "phone": b.phone or "—",
                    "whatsapp": wa_link or "—",
                    "emails": "<br>".join(emails) if emails else "*None*",
                    "industry": b.industry or "General",
                    "rating": f"★ {b.rating}" if b.rating else "—"
                })

        md = [
            f"### LeadForge Database Search ({len(results)} matches)\n",
            "| ID | Business Name | Google Maps | Phone | WhatsApp | Category | Emails | Rating |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for r in results:
            name_clean = r["name"].replace("|", "\\|")
            maps_link = f"[Maps]({r['maps_url']})"
            md.append(f"| #{r['id']} | **{name_clean}** | {maps_link} | {r['phone']} | {r['whatsapp']} | {r['industry']} | {r['emails']} | {r['rating']} |")

        return "\n".join(md)

    elif name == "leadforge_enrich_lead":
        business_id = int(arguments["business_id"])
        res = await enrich_business_by_id(business_id)

        return (
            f"### Multi-Source Enrichment Completed for ID #{business_id}\n"
            f"• **Business**: {res.get('name', 'Unknown')}\n"
            f"• **Emails Found**: {res.get('emails_found', 0)} ({res.get('verified_emails', 0)} verified deliverable)\n"
            f"• **Phone Numbers Discovered**: {res.get('phones_found', 0)}\n"
            f"• **Discovered Website**: {res.get('website') or 'None'}\n"
            f"• **Social Profiles**: {json.dumps(res.get('socials', {}))}"
        )

    elif name == "leadforge_create_campaign":
        c_name = arguments["name"]
        steps_input = arguments["steps"]

        async with async_session_maker() as db:
            camp = Campaign(name=c_name, status="draft")
            db.add(camp)
            await db.flush()

            for idx, s in enumerate(steps_input):
                step = CampaignStep(
                    campaign_id=camp.id,
                    step_order=idx + 1,
                    subject=s["subject"],
                    body_text=s["body_text"],
                    body_html=s.get("body_html"),
                    delay_days=s.get("delay_days", 0)
                )
                db.add(step)

            await db.commit()
            await db.refresh(camp)

        return f"Successfully created campaign '{c_name}' (ID: #{camp.id}) with {len(steps_input)} sequence steps. Status: Draft."

    elif name == "leadforge_get_stats":
        async with async_session_maker() as db:
            res_b = await db.execute(select(func.count(Business.id)))
            total_leads = res_b.scalar() or 0
            res_c = await db.execute(select(func.count(Contact.id)))
            total_contacts = res_c.scalar() or 0
            res_v = await db.execute(select(func.count(Contact.id)).where(Contact.is_verified == True))
            verified_contacts = res_v.scalar() or 0
            res_camp = await db.execute(select(func.count(Campaign.id)))
            total_camps = res_camp.scalar() or 0

        return (
            "### LeadForge Overview\n"
            f"• **Total Discovered Businesses**: {total_leads}\n"
            f"• **Total Contacts (Phones/Emails)**: {total_contacts}\n"
            f"• **SMTP-Verified Deliverable Emails**: {verified_contacts}\n"
            f"• **Outreach Campaigns**: {total_camps}\n"
            "• **Dashboard**: [http://localhost:3000](http://localhost:3000)\n"
            "• **Backend API**: [http://localhost:8000](http://localhost:8000)"
        )

    else:
        raise ValueError(f"Unknown tool: {name}")


async def run_mcp_server():
    """Runs the Model Context Protocol stdio loop."""
    logger.info("Starting LeadForge MCP stdio server...")

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break

        line_str = line.decode("utf-8").strip()
        if not line_str:
            continue

        try:
            req = json.loads(line_str)
        except Exception as parse_err:
            logger.error(f"JSON decode error: {parse_err}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        response = None

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "leadforge",
                        "version": "1.0.0"
                    }
                }
            }
        elif method == "notifications/initialized":
            # Notification only, no reply required
            continue
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS_DEFINITIONS
                }
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result_text = await handle_tool_call(tool_name, tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text
                            }
                        ]
                    }
                }
            except Exception as tool_err:
                logger.error(f"Error executing tool {tool_name}: {tool_err}")
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": str(tool_err)
                    }
                }
        elif method == "ping":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            if req_id is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found"
                    }
                }

        if response:
            out_bytes = (json.dumps(response) + "\n").encode("utf-8")
            sys.stdout.buffer.write(out_bytes)
            sys.stdout.buffer.flush()


def main():
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
