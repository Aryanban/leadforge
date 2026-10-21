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
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List, Optional, Sequence, Set

# Ensure backend directory is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, or_, func
from app.database import async_session_maker, ensure_schema
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep, CampaignTarget
from app.models.mailbox import Mailbox
from app.models.send import Send
from app.models.suppression import Suppression, PERMANENT_REASONS
from app.scraper.maps_scraper import scrape_leads_and_save
from app.enricher.email_finder import enrich_business_by_id
from app.campaigns.sender import execute_campaign_step, test_smtp_connection
from app.campaigns.suppression import add_suppression, filter_suppressed
from app.verifier.smtp_verifier import verify_email_async
from app.verifier.email_status import should_send

# Configure logging to stderr so stdout remains clean for JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("leadforge-mcp")

# Strong references to fire-and-forget campaign-dispatch tasks so the event loop
# does not garbage-collect them mid-run (Python keeps only weak refs to running
# asyncio tasks). Mirrors the API's BackgroundTasks launch, which also detaches.
_BACKGROUND_TASKS = set()

#: How long the stdio loop waits for in-flight requests to write their
#: response after stdin reaches EOF, before it cancels the stragglers.
_SHUTDOWN_GRACE_SECONDS = 10.0

#: Progress percentage per scrape-job status, so a polling agent gets a
#: number it can chart instead of guessing from a string.
_SCRAPE_JOB_PROGRESS = {
    "pending": 0,
    "running": 20,
    "scraping": 40,
    "enriching": 80,
    "completed": 100,
    "failed": 100,
}


TOOLS_DEFINITIONS = [
    {
        "name": "leadforge_scrape",
        "description": "Starts a Google Maps scrape in the BACKGROUND and returns a job handle immediately. Scrapes business listings in real-time, extracts phone numbers, ratings, addresses and official websites, discovers emails from across the open web, and saves everything to the database. Because a full scrape plus enrichment takes minutes (far past the ~60s MCP client tool timeout) this tool does NOT block: it returns a job_id and you must poll `leadforge_get_scrape_job` until the status is 'completed'.",
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
        "name": "leadforge_get_scrape_job",
        "description": "Polls a scrape job started by `leadforge_scrape`. Returns the job status, progress percentage, how many leads were found and saved, and - once the job is 'completed' - the leads it produced with their Contact IDs (use those with `leadforge_add_campaign_targets`; a Contact ID is NOT the Business ID).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "integer",
                    "description": "The job_id returned by `leadforge_scrape`"
                }
            },
            "required": ["job_id"]
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
    },
    {
        "name": "leadforge_check_spam",
        "description": "Analyzes cold email subject and body copy for spam trigger words, all-caps flags, link density, and deliverability hygiene.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Subject line"},
                "body": {"type": "string", "description": "Email body copy"}
            },
            "required": ["subject", "body"]
        }
    },
    {
        "name": "leadforge_generate_icebreaker",
        "description": "Generates Apollo/Clay-grade personalized cold outreach icebreaker hooks, compliments, and pain points for a business lead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "business_id": {"type": "integer", "description": "Lead business ID in database"},
                "business_name": {"type": "string", "description": "Business name (if not using ID)"},
                "industry": {"type": "string", "description": "Industry / niche"},
                "city": {"type": "string", "description": "City or territory"}
            }
        }
    },

    # --- Agent automation loop: targets -> launch -> monitor -> pause ------
    {
        "name": "leadforge_list_campaigns",
        "description": "Lists all campaigns with status, step count, explicit recipient (target) count, and total sends.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "leadforge_get_campaign",
        "description": "Gets one campaign: status, sequence steps, target count, and recent sends (reply/status flags).",
        "inputSchema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "integer", "description": "Campaign ID"}},
            "required": ["campaign_id"]
        }
    },
    {
        "name": "leadforge_add_campaign_targets",
        "description": "Adds contacts (by ID) as explicit recipients of a campaign (Apollo 'Add to Sequence'). Idempotent; suppressed contacts are skipped. A campaign needs targets before launch or it is refused.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "Campaign ID"},
                "contact_ids": {"type": "array", "items": {"type": "integer"}, "description": "Contact IDs to add"}
            },
            "required": ["campaign_id", "contact_ids"]
        }
    },
    {
        "name": "leadforge_launch_campaign",
        "description": "Activates a campaign and dispatches its sequence in the background. Refuses to launch with 0 targets or 0 steps to avoid emailing the whole database. Honors suppression, warmup/health, daily limits, delays, and send jitter. Performs a DRY RUN by default - it returns the exact recipient list and subject lines without sending anything. Set dry_run=false only when the operator has explicitly approved the send.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "Campaign ID"},
                "dry_run": {
                    "type": "boolean",
                    "description": "When true (the default), preview the recipients and subject lines WITHOUT sending. Set to false to actually send.",
                    "default": True,
                },
            },
            "required": ["campaign_id"]
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}
    },
    {
        "name": "leadforge_pause_campaign",
        "description": "Pauses an active campaign; no sends go out until relaunched.",
        "inputSchema": {
            "type": "object",
            "properties": {"campaign_id": {"type": "integer", "description": "Campaign ID"}},
            "required": ["campaign_id"]
        }
    },

    # --- Mailboxes ---------------------------------------------------------
    {
        "name": "leadforge_list_mailboxes",
        "description": "Lists sending mailboxes with SMTP host/port, sent/daily-limit, active flag, and health score.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "leadforge_create_mailbox",
        "description": "Adds an SMTP sending mailbox. Daily limit is capped at 50 for warmup safety. Optionally runs a live SMTP login test.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Mailbox email / login user"},
                "password": {"type": "string", "description": "SMTP or app-specific password"},
                "smtp_host": {"type": "string", "description": "e.g. smtp.gmail.com"},
                "smtp_port": {"type": "integer", "description": "587 STARTTLS, 465 SSL", "default": 587},
                "first_name": {"type": "string", "description": "Sender first name"},
                "last_name": {"type": "string", "description": "Sender last name"},
                "daily_limit": {"type": "integer", "description": "Max sends/day (capped 50)", "default": 50},
                "test_connection": {"type": "boolean", "description": "Run a live SMTP login test", "default": True}
            },
            "required": ["email", "password", "smtp_host"]
        }
    },

    # --- Verification & suppression ---------------------------------------
    {
        "name": "leadforge_verify_email",
        "description": "Verifies an email via syntax/role/free classification, DNS MX, and SMTP handshake. Never coerces an unknown into valid.",
        "inputSchema": {
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email to verify"}},
            "required": ["email"]
        }
    },
    {
        "name": "leadforge_list_suppression",
        "description": "Lists the global suppression list (addresses/domains never to be mailed) with reason and active/expired state.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "leadforge_add_suppression",
        "description": "Adds an address (or whole domain if it starts with '@') to the global suppression list. Workspace-wide do-not-contact / unsubscribe control.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Email, or '@domain.com' for a whole domain"},
                "reason": {"type": "string", "description": "unsubscribed, replied_stop, hard_bounce, soft_bounce, complaint, manual, import", "default": "manual"},
                "detail": {"type": "string", "description": "Optional note"},
                "domain_wide": {"type": "boolean", "description": "Treat identifier as a domain (auto-on when it starts with '@')"}
            },
            "required": ["identifier"]
        }
    }
]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def _contacts_by_business(
    db: Any, business_ids: Sequence[int]
) -> Dict[int, List[Contact]]:
    """Fetches the contacts of every business on a page in ONE query.

    The handlers used to run ``SELECT ... FROM contacts WHERE business_id = ?``
    once per business, so a 15-row page cost 16 round-trips instead of 2. On
    a slow link (a self-hosted box on a Raspberry Pi, or Postgres over the
    internet) that is the difference between 40ms and 900ms for the same
    page - and it scaled linearly with the page size.

    Returns a dict keyed by ``business_id``; businesses with no contacts are
    simply absent from it.
    """
    ids: List[int] = []
    seen: Set[int] = set()
    for bid in business_ids or []:
        if bid is None:
            continue
        bid = int(bid)
        if bid not in seen:
            seen.add(bid)
            ids.append(bid)
    if not ids:
        return {}

    rows = (await db.execute(
        select(Contact).where(Contact.business_id.in_(ids))
    )).scalars().all()

    grouped: Dict[int, List[Contact]] = defaultdict(list)
    for c in rows:
        grouped[c.business_id].append(c)
    return dict(grouped)


def _contact_summary(contacts: Sequence[Contact]) -> Dict[str, Any]:
    """The contact fields an agent needs to target a lead."""
    return {
        "contact_ids": [c.id for c in contacts],
        "primary_contact_id": next(
            (c.id for c in contacts if c.email),
            contacts[0].id if contacts else None,
        ),
        "emails": [
            f"`{c.email}`" + (" (✓ deliverable)" if c.is_verified else "")
            for c in contacts if c.email
        ],
    }


# ---------------------------------------------------------------------------
# Background scrape job
# ---------------------------------------------------------------------------

async def _mark_scrape_job(
    job_id: int, *, status: str, error: Optional[str] = None
) -> None:
    """Records a terminal state on a scrape job row. Never raises."""
    try:
        async with async_session_maker() as db:
            job = await db.get(ScrapeJob, job_id)
            if job is None:
                return
            # Never downgrade a finished job.
            if job.status in ("completed", "failed") and status != job.status:
                return
            job.status = status
            if error:
                job.error = error
            if status in ("completed", "failed"):
                job.finished_at = datetime.utcnow()
            await db.commit()
    except Exception:
        logger.exception("Could not update scrape job %s", job_id)


async def _run_scrape_job(
    job_id: int, query: str, max_results: int, auto_enrich: bool
) -> None:
    """Runs a scrape in the background and records the outcome on the job row.

    The scrape used to run INLINE inside the tool call, which held the
    JSON-RPC read loop for the whole scrape + enrichment waterfall. Every
    other request queued behind it, and MCP clients (Claude Desktop) time a
    tool call out at ~60s - so the tool always looked like a failure.
    """
    try:
        saved_count, new_biz_ids = await scrape_leads_and_save(
            query=query,
            max_results=max_results,
            job_id=job_id,
            enrich=auto_enrich,
        )
        # Remember which businesses this job produced so
        # `leadforge_get_scrape_job` can hand the agent the exact leads
        # (and their Contact IDs) without a second, lossy search.
        try:
            async with async_session_maker() as db:
                job = await db.get(ScrapeJob, job_id)
                if job is not None:
                    result = dict(job.result or {})
                    result["business_ids"] = list(new_biz_ids or [])
                    result["leads_saved"] = saved_count
                    job.result = result
                    if job.status == "completed" and not job.finished_at:
                        job.finished_at = datetime.utcnow()
                    await db.commit()
        except Exception:
            logger.exception("Could not record scrape job %s results", job_id)
    except asyncio.CancelledError:
        # The server is shutting down mid-scrape. Mark the job so it does
        # not sit at "running" forever and mislead a later poll.
        try:
            await _mark_scrape_job(
                job_id, status="failed", error="scrape interrupted (server shut down)"
            )
        except Exception:
            pass
        raise
    except Exception as exc:
        logger.exception("Scrape job %s failed", job_id)
        await _mark_scrape_job(
            job_id, status="failed", error=f"{type(exc).__name__}: {exc}"
        )


async def _scrape_job_leads(db: Any, job: ScrapeJob) -> List[Dict[str, Any]]:
    """The businesses a finished scrape job produced, with their contacts."""
    business_ids = list((job.result or {}).get("business_ids") or [])
    if not business_ids:
        return []

    businesses = (await db.execute(
        select(Business).where(Business.id.in_(business_ids)).order_by(Business.id)
    )).scalars().all()

    contacts_by_biz = await _contacts_by_business(db, [b.id for b in businesses])

    rows: List[Dict[str, Any]] = []
    for b in businesses:
        contacts = contacts_by_biz.get(b.id, [])
        summary = _contact_summary(contacts)
        clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
        maps_url = b.maps_url or (
            "https://www.google.com/maps/search/?api=1&query="
            f"{urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"
        )
        rows.append({
            "business_id": b.id,
            "contact_ids": summary["contact_ids"],
            "primary_contact_id": summary["primary_contact_id"],
            "name": b.name,
            "maps_url": maps_url,
            "phone": b.phone or "—",
            "whatsapp": f"https://wa.me/{clean_phone}" if clean_phone else "—",
            "website": b.website or "—",
            "emails": summary["emails"],
            "rating": f"★ {b.rating}" if b.rating else "—",
            "address": b.address or "—",
        })
    return rows


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Executes an MCP tool and returns markdown-formatted response for the AI assistant."""

    if name == "leadforge_scrape":
        query = arguments.get("query")
        if not query:
            raise ValueError("`query` is required for leadforge_scrape")
        max_results = min(int(arguments.get("max_results", 10)), 50)
        auto_enrich = bool(arguments.get("auto_enrich", True))

        # Create the job row FIRST so the caller gets a handle it can poll
        # immediately, then run the scrape in the BACKGROUND.
        #
        # The scrape used to run inline, which held the JSON-RPC read loop for
        # the whole scrape + enrichment waterfall (minutes). MCP clients
        # (Claude Desktop) time a tool call out at ~60s, so the tool always
        # looked like a failure and every other request queued behind it.
        async with async_session_maker() as db:
            job = ScrapeJob(query=query, status="pending")
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        task = asyncio.ensure_future(
            _run_scrape_job(job_id, query, max_results, auto_enrich)
        )
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

        return json.dumps({
            "job_id": job_id,
            "status": "running",
            "query": query,
            "max_results": max_results,
            "auto_enrich": auto_enrich,
            "poll": "leadforge_get_scrape_job",
            "message": (
                "Scrape started in the background. Poll `leadforge_get_scrape_job` "
                f"with job_id {job_id} until status is 'completed' (or 'failed'). "
                "The results, including the Contact IDs you need for "
                "`leadforge_add_campaign_targets`, come back with the job."
            ),
        }, indent=2)

    elif name == "leadforge_get_scrape_job":
        job_id = int(arguments["job_id"])
        async with async_session_maker() as db:
            job = await db.get(ScrapeJob, job_id)
            if not job:
                return json.dumps({
                    "job_id": job_id,
                    "error": f"Scrape job #{job_id} not found",
                }, indent=2)

            status = job.status or "pending"
            payload: Dict[str, Any] = {
                "job_id": job.id,
                "query": job.query,
                "status": status,
                "progress_pct": _SCRAPE_JOB_PROGRESS.get(status, 0),
                "done": status in ("completed", "failed"),
                "total_found": job.total_found or 0,
                "leads_saved": job.leads_saved or 0,
                "error": job.error,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }

            if status == "completed":
                payload["leads"] = await _scrape_job_leads(db, job)
            else:
                payload["leads"] = []

        if status == "completed":
            payload["message"] = (
                "Scrape finished. Use the `contact_ids` / `primary_contact_id` of "
                "each lead with `leadforge_add_campaign_targets` - a Contact ID "
                "is NOT the Business ID."
            )
        elif status == "failed":
            payload["message"] = (
                "Scrape failed. Check `error`, fix the cause and start a new one "
                "with `leadforge_scrape`."
            )
        else:
            payload["message"] = (
                "Scrape still running. Wait a few seconds and poll this tool "
                "again with the same job_id."
            )

        return json.dumps(payload, indent=2)

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

            # The "has email" filter is a SQL predicate applied BEFORE the
            # limit. Filtering after the limit made the tool's own limit
            # parameter change its answer: asking for 5 leads with
            # has_email=true returned 0 matches, while asking for 100
            # returned 6 - the filter was applied to an already-truncated set.
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

            # ONE query for the contacts of the whole page, not one per row.
            contacts_by_biz = await _contacts_by_business(db, [b.id for b in businesses])

            results = []
            for b in businesses:
                contacts = contacts_by_biz.get(b.id, [])
                summary = _contact_summary(contacts)

                clean_phone = (b.phone or "").replace(" ", "").replace("-", "")
                wa_link = f"[WhatsApp](https://wa.me/{clean_phone})" if clean_phone else ""
                maps_url = b.maps_url or f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote((b.name + ' ' + (b.address or '')).strip())}"

                results.append({
                    "id": b.id,
                    # Contact ids are what `add_campaign_targets` needs.
                    "contact_ids": summary["contact_ids"],
                    "primary_contact_id": summary["primary_contact_id"],
                    "name": b.name,
                    "maps_url": maps_url,
                    "phone": b.phone or "—",
                    "whatsapp": wa_link or "—",
                    "emails": "<br>".join(summary["emails"]) if summary["emails"] else "*None*",
                    "industry": b.industry or "General",
                    "rating": f"★ {b.rating}" if b.rating else "—"
                })

        md = [
            f"### LeadForge Database Search ({len(results)} matches)\n",
            "| Business ID | Contact ID | Business Name | Google Maps | Phone | WhatsApp | Category | Emails | Rating |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for r in results:
            name_clean = r["name"].replace("|", "\\|")
            maps_link = f"[Maps]({r['maps_url']})"
            contact_id = r["primary_contact_id"] if r["primary_contact_id"] else "—"
            md.append(
                f"| #{r['id']} | {contact_id} | **{name_clean}** | {maps_link} | {r['phone']} "
                f"| {r['whatsapp']} | {r['industry']} | {r['emails']} | {r['rating']} |"
            )

        md.append(
            "\n> Use the **Contact ID** column with `leadforge_add_campaign_targets` "
            "to enroll these leads in a sequence. The Contact ID is NOT the "
            "Business ID."
        )

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
                    step_number=idx + 1,
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

    elif name == "leadforge_check_spam":
        from app.campaigns.spam_checker import check_cold_email_spam
        subject = arguments.get("subject", "")
        body = arguments.get("body", "")
        result = check_cold_email_spam(subject, body)

        lines = [
            "### LeadForge Deliverability & Spam Scorecard\n",
            f"• **Score**: {result['score']}/100 ({result['tier']})",
            f"• **Safe to Send**: {'✓ Yes' if result['is_safe'] else '⚠ Caution / High Risk'}",
            f"• **Subject Word Count**: {result['subject_word_count']} words",
            f"• **Link Count**: {result['link_count']}",
            f"• **Personalization Detected**: {'✓ Yes' if result['has_personalization'] else 'None'}\n"
        ]

        if result["high_risk_words"]:
            lines.append(f"**High-Risk Triggers**: `{', '.join(result['high_risk_words'])}`")
        if result["moderate_risk_words"]:
            lines.append(f"**Promotional Words**: `{', '.join(result['moderate_risk_words'])}`")
        if result["warnings"]:
            lines.append("\n**Warnings & Recommendations**:")
            for w in result["warnings"]:
                lines.append(f"- ⚠ {w}")
            for r in result["recommendations"]:
                lines.append(f"- 💡 {r}")

        return "\n".join(lines)

    elif name == "leadforge_generate_icebreaker":
        from app.enricher.ai_icebreaker import generate_ai_icebreaker
        b_id = arguments.get("business_id")
        b_name = arguments.get("business_name")
        industry = arguments.get("industry")
        city = arguments.get("city", "Delhi NCR")

        if b_id:
            async with async_session_maker() as db:
                b = await db.get(Business, int(b_id))
                if b:
                    b_name = b.name
                    industry = b.industry or industry
                    c_stmt = select(Contact).where(Contact.business_id == b.id).limit(1)
                    c_res = await db.execute(c_stmt)
                    c = c_res.scalars().first()
                    first_name = c.first_name if c else None
                    info = generate_ai_icebreaker(
                        business_name=b.name,
                        industry=b.industry,
                        city=city,
                        rating=b.rating,
                        reviews_count=b.reviews_count,
                        website=b.website,
                        first_name=first_name
                    )
                else:
                    info = generate_ai_icebreaker(business_name=b_name or f"Business #{b_id}", industry=industry, city=city)
        else:
            info = generate_ai_icebreaker(business_name=b_name or "Your Business", industry=industry, city=city)

        return (
            f"### AI Personalized Icebreaker for {info['business_name']}\n\n"
            f"**Opening Hook (Angle 1)**:\n> {info['full_opening_hook']}\n\n"
            f"**Alternative Hook (Angle 2)**:\n> {info['alternative_hook']}\n\n"
            f"**Authentic Compliment**: {info['compliment']}\n"
            f"**Identified Pain Point**: {info['pain_point']}\n"
            f"**Low-Friction Call-To-Action**: {info['call_to_action']}\n\n"
            f"*Variables exported*: `{{{{ai_icebreaker}}}}`, `{{{{compliment}}}}`, `{{{{pain_point}}}}`, `{{{{call_to_action}}}}`"
        )

    # --- Agent automation loop: list -> inspect -> target -> launch -> pause --
    elif name == "leadforge_list_campaigns":
        async with async_session_maker() as db:
            camps = (await db.execute(
                select(Campaign).order_by(Campaign.created_at.desc())
            )).scalars().all()

            # THREE grouped aggregate queries for the whole page instead of
            # three COUNT queries per campaign. The old shape was 1 + 3N
            # round-trips, so a 20-campaign workspace cost 61 queries to
            # render one table.
            camp_ids = [c.id for c in camps]
            step_counts: Dict[int, int] = {}
            target_counts: Dict[int, int] = {}
            send_counts: Dict[int, int] = {}
            if camp_ids:
                step_counts = dict((await db.execute(
                    select(CampaignStep.campaign_id, func.count(CampaignStep.id))
                    .where(CampaignStep.campaign_id.in_(camp_ids))
                    .group_by(CampaignStep.campaign_id)
                )).all())
                target_counts = dict((await db.execute(
                    select(CampaignTarget.campaign_id, func.count(CampaignTarget.id))
                    .where(CampaignTarget.campaign_id.in_(camp_ids))
                    .group_by(CampaignTarget.campaign_id)
                )).all())
                send_counts = dict((await db.execute(
                    select(Send.campaign_id, func.count(Send.id))
                    .where(Send.campaign_id.in_(camp_ids))
                    .group_by(Send.campaign_id)
                )).all())

            rows = [
                (
                    camp,
                    step_counts.get(camp.id, 0),
                    target_counts.get(camp.id, 0),
                    send_counts.get(camp.id, 0),
                )
                for camp in camps
            ]

        if not rows:
            return ("### LeadForge Campaigns\n\nNo campaigns yet. "
                    "Use `leadforge_create_campaign` to build one.")
        md = [
            f"### LeadForge Campaigns ({len(rows)})\n",
            "| ID | Name | Status | Steps | Targets | Sends |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for camp, steps, targets, sends in rows:
            name_clean = (camp.name or "").replace("|", "\\|")
            md.append(f"| #{camp.id} | **{name_clean}** | {camp.status} | {steps} | {targets} | {sends} |")
        return "\n".join(md)

    elif name == "leadforge_get_campaign":
        campaign_id = int(arguments["campaign_id"])
        async with async_session_maker() as db:
            camp = await db.get(Campaign, campaign_id)
            if not camp:
                return f"Campaign #{campaign_id} not found."

            steps = (await db.execute(
                select(CampaignStep).where(CampaignStep.campaign_id == campaign_id)
                .order_by(CampaignStep.step_number.asc())
            )).scalars().all()

            targets = (await db.execute(
                select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign_id)
            )).scalar() or 0

            sends = (await db.execute(
                select(Send).where(Send.campaign_id == campaign_id)
                .order_by(Send.created_at.desc()).limit(50)
            )).scalars().all()

            camp_name = camp.name
            camp_status = camp.status

        sent = sum(1 for s in sends if s.status == "sent")
        bounced = sum(1 for s in sends if s.status == "bounced")
        failed = sum(1 for s in sends if s.status == "failed")
        replied = sum(1 for s in sends if s.replied)

        lines = [
            f"### Campaign #{campaign_id}: {camp_name}\n",
            f"• **Status**: {camp_status}",
            f"• **Targets**: {targets} explicit recipient(s)",
            f"• **Recent Sends**: {len(sends)} (sent {sent} · bounced {bounced} · "
            f"failed {failed} · replied {replied})\n",
            "**Sequence Steps**:",
        ]
        if steps:
            for s in steps:
                delay = f" (+{s.delay_days}d)" if s.delay_days else ""
                lines.append(f"- Step {s.step_number}{delay}: {s.subject}")
        else:
            lines.append("- *No steps configured*")

        if sends:
            lines.append("\n**Recent Sends**:")
            for s in sends[:15]:
                flag = " ↩ replied" if s.replied else (" ✉ opened" if s.opened else "")
                err = f" — {s.error_message}" if s.error_message else ""
                lines.append(f"- #{s.id}: `{s.status}`{flag}{err}")

        return "\n".join(lines)

    elif name == "leadforge_add_campaign_targets":
        campaign_id = int(arguments["campaign_id"])
        contact_ids = [int(c) for c in (arguments.get("contact_ids") or [])]
        if not contact_ids:
            return "No contact IDs provided."

        async with async_session_maker() as db:
            camp = await db.get(Campaign, campaign_id)
            if not camp:
                return f"Campaign #{campaign_id} not found."

            existing = {row[0] for row in (await db.execute(
                select(CampaignTarget.contact_id).where(CampaignTarget.campaign_id == campaign_id)
            )).all()}

            # ONE query for every contact id, and ONE query for the whole
            # suppression list. The old shape ran a SELECT per contact id and
            # a suppression SELECT per contact - so adding 50 targets cost
            # 100+ round-trips.
            unique_ids = list(dict.fromkeys(contact_ids))
            contacts = (await db.execute(
                select(Contact).where(Contact.id.in_(unique_ids))
            )).scalars().all()
            contacts_by_id = {c.id: c for c in contacts}

            candidates = [
                contacts_by_id[cid] for cid in unique_ids
                if cid in contacts_by_id and cid not in existing
            ]
            blocked = await filter_suppressed(db, [c.email for c in candidates])

            added = 0
            skipped = 0
            missing = 0
            for cid in unique_ids:
                if cid in existing:
                    continue
                # Gate 1 of 4: never add an already-suppressed address as a target.
                contact = contacts_by_id.get(cid)
                if contact is None:
                    # A non-existent contact id used to be silently dropped
                    # and NOT counted, so the tool reported "Added 0 target(s)
                    # (0 skipped)" and the agent concluded success.
                    missing += 1
                    continue
                if contact.email and contact.email.strip().lower() in blocked:
                    skipped += 1
                    continue
                db.add(CampaignTarget(campaign_id=campaign_id, contact_id=cid))
                added += 1
            await db.commit()

            total = (await db.execute(
                select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign_id)
            )).scalar() or 0

        parts = [f"Added {added} target(s) to campaign #{campaign_id}"]
        if skipped:
            parts.append(f"({skipped} skipped: suppressed)")
        if missing:
            parts.append(
                f"**WARNING: {missing} contact id(s) did not exist and were skipped** - "
                "check that you are using Contact IDs (from the Contact ID column) "
                "and not Business IDs."
            )
        parts.append(f"Total targets: {total}.")
        return " ".join(parts)

    elif name == "leadforge_launch_campaign":
        campaign_id = int(arguments["campaign_id"])
        # Dry run by default. An autonomous agent firing real cold email at
        # real people without a human in the loop is the single most
        # dangerous thing this server can do, and the tool had no way to
        # preview what would be sent.
        dry_run = arguments.get("dry_run", True)
        async with async_session_maker() as db:
            camp = await db.get(Campaign, campaign_id)
            if not camp:
                return f"Campaign #{campaign_id} not found."
            steps = (await db.execute(
                select(func.count(CampaignStep.id)).where(CampaignStep.campaign_id == campaign_id)
            )).scalar() or 0
            targets = (await db.execute(
                select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == campaign_id)
            )).scalar() or 0
            if steps == 0:
                return (f"Campaign #{campaign_id} cannot launch: no sequence steps. "
                        "Create steps with `leadforge_create_campaign` first.")
            if targets == 0:
                return (f"Campaign #{campaign_id} cannot launch: no explicit targets. "
                        "Add recipients with `leadforge_add_campaign_targets` so we never "
                        "mail leads the operator did not pick.")

            # Preview the exact recipients and subject lines.
            recipient_rows = (await db.execute(
                select(Contact.email, Contact.first_name)
                .join(CampaignTarget, CampaignTarget.contact_id == Contact.id)
                .where(CampaignTarget.campaign_id == campaign_id)
            )).all()
            step_rows = (await db.execute(
                select(CampaignStep.step_number, CampaignStep.subject)
                .where(CampaignStep.campaign_id == campaign_id)
                .order_by(CampaignStep.step_number)
            )).all()

            if dry_run:
                preview = [f"**DRY RUN - nothing was sent.**",
                           f"Campaign #{campaign_id} would send {targets} email(s) "
                           f"across {steps} step(s).",
                           "",
                           "**Recipients (first 10):**"]
                for email, first_name in recipient_rows[:10]:
                    preview.append(f"- {first_name or '—'} <{email}>")
                if len(recipient_rows) > 10:
                    preview.append(f"- ...and {len(recipient_rows) - 10} more")
                preview.append("")
                preview.append("**Steps:**")
                for num, subject in step_rows:
                    preview.append(f"- Step {num}: {subject}")
                preview.append("")
                preview.append("Re-call with `dry_run=false` to actually send.")
                return "\n".join(preview)

            if camp.status == CampaignStatus.ACTIVE.value:
                return (f"Campaign #{campaign_id} is already active - not launching a "
                        "second sender (that would double-send to the same leads).")
            camp.status = CampaignStatus.ACTIVE.value
            camp_name = camp.name
            await db.commit()
        task = asyncio.ensure_future(execute_campaign_step(campaign_id))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return (f"Campaign '{camp_name}' (#{campaign_id}) launched: {targets} target(s) "
                f"across {steps} step(s). Sends dispatch in the background (suppression, "
                "warmup/health, daily limits, delays, jitter). Poll `leadforge_get_campaign`.")

    elif name == "leadforge_pause_campaign":
        campaign_id = int(arguments["campaign_id"])
        async with async_session_maker() as db:
            camp = await db.get(Campaign, campaign_id)
            if not camp:
                return f"Campaign #{campaign_id} not found."
            camp.status = CampaignStatus.PAUSED.value
            camp_name = camp.name
            await db.commit()
        return (f"Campaign '{camp_name}' (#{campaign_id}) paused. "
                "No sends go out until `leadforge_launch_campaign`.")

    elif name == "leadforge_list_mailboxes":
        async with async_session_maker() as db:
            mailboxes = (await db.execute(
                select(Mailbox).order_by(Mailbox.id.desc())
            )).scalars().all()
            rows = [(m.id, m.email, m.smtp_host, m.smtp_port, m.sent_today,
                     m.daily_limit, bool(m.is_active), m.health_score,
                     bool(getattr(m, "health_paused", False))) for m in mailboxes]
        if not rows:
            return ("### LeadForge Mailboxes\n\nNo sending mailboxes yet. "
                    "Add one with `leadforge_create_mailbox` before launching.")
        md = [
            f"### LeadForge Mailboxes ({len(rows)})\n",
            "| ID | Email | SMTP | Sent / Limit | State | Health |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for mid, email, host, port, sent, limit, active, health, paused in rows:
            host_str = f"{host}:{port}" if host else "—"
            state = "active" if active else "inactive"
            if paused:
                state += " · health-paused"
            health_str = f"{health:.2f}" if health is not None else "—"
            md.append(f"| #{mid} | {email} | {host_str} | {sent} / {limit} | {state} | {health_str} |")
        return "\n".join(md)

    elif name == "leadforge_create_mailbox":
        email = (arguments.get("email") or "").strip()
        password = arguments.get("password") or ""
        smtp_host = (arguments.get("smtp_host") or "").strip()
        smtp_port = int(arguments.get("smtp_port", 587))
        first_name = arguments.get("first_name")
        last_name = arguments.get("last_name")
        daily_limit = min(int(arguments.get("daily_limit", 50)), 50)
        test_connection = arguments.get("test_connection", True)
        if not email or not smtp_host:
            return "Both `email` and `smtp_host` are required."
        if test_connection:
            ok, msg = test_smtp_connection(smtp_host, smtp_port, email, password)
            if not ok:
                return (f"SMTP login test failed for {email} at {smtp_host}:{smtp_port}: {msg}\n"
                        "Mailbox NOT saved. Fix credentials/host and retry, or pass "
                        "`test_connection: false` to save without testing.")
        async with async_session_maker() as db:
            existing = (await db.execute(
                select(Mailbox).where(Mailbox.email == email)
            )).scalars().first()
            if existing:
                return f"A mailbox with email {email} already exists (ID: #{existing.id})."
            mb = Mailbox(email=email, password=password, smtp_host=smtp_host,
                         smtp_port=smtp_port, first_name=first_name,
                         last_name=last_name, daily_limit=daily_limit, is_active=True)
            db.add(mb)
            await db.commit()
            await db.refresh(mb)
            mb_id = mb.id
        note = " Live SMTP login test passed." if test_connection else ""
        return (f"Mailbox {email} saved (ID: #{mb_id}) on {smtp_host}:{smtp_port}, "
                f"daily limit {daily_limit} (capped 50 for warmup).{note}")

    elif name == "leadforge_verify_email":
        email = (arguments.get("email") or "").strip()
        if not email:
            return "An `email` to verify is required."
        result = await verify_email_async(email)
        verdict = "✓ safe to send" if should_send(result) else "✗ do not send"
        lines = [
            f"### Email Verification: {email}\n",
            f"• **Status**: {result.status.value} ({result.sub_status})",
            f"• **Confidence**: {result.confidence:.2f}",
            f"• **Verdict**: {verdict}",
        ]
        if result.is_role:
            lines.append("• **Role account**: yes (info@/sales@ style)")
        if result.is_free:
            lines.append("• **Free provider**: yes (gmail/yahoo style)")
        if result.mx_host:
            lines.append(f"• **MX host**: {result.mx_host}")
        if result.detail:
            lines.append(f"• **Detail**: {result.detail}")
        return "\n".join(lines)

    elif name == "leadforge_list_suppression":
        async with async_session_maker() as db:
            rows = (await db.execute(
                select(Suppression).order_by(Suppression.id.desc()).limit(200)
            )).scalars().all()
            entries = [(r.identifier, r.reason, r.detail, r.is_active()) for r in rows]
        if not entries:
            return ("### LeadForge Suppression List\n\nThe suppression list is empty — "
                    "no addresses are blocked workspace-wide yet.")
        md = [
            f"### LeadForge Suppression List ({len(entries)})\n",
            "| Identifier | Reason | State | Detail |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for ident, reason, detail, active in entries:
            state = "active" if active else "expired"
            md.append(f"| `{ident}` | {reason} | {state} | {detail or '—'} |")
        return "\n".join(md)

    elif name == "leadforge_add_suppression":
        identifier = (arguments.get("identifier") or "").strip()
        reason = (arguments.get("reason") or "manual").strip()
        detail = arguments.get("detail")
        domain_wide = bool(arguments.get("domain_wide", False)) or identifier.startswith("@")
        if not identifier:
            return "An `identifier` (email or '@domain.com') is required."
        if domain_wide and "@" not in identifier:
            return ("For a whole-domain block, pass the domain as '@domain.com' "
                    "so the blocked key is unambiguous.")
        async with async_session_maker() as db:
            newly = await add_suppression(db, identifier, reason, detail=detail,
                                          domain_wide=domain_wide)
            await db.commit()
        scope = "whole domain" if domain_wide else "address"
        key = (f"@{identifier.rsplit('@', 1)[-1]}" if domain_wide
               else identifier.strip().lower())
        verb = "Added" if newly else "Updated existing"
        return (f"{verb} suppression: {scope} `{key}` (reason: {reason}) is now blocked "
                "workspace-wide. It is enforced at the queue gate before any SMTP send.")

    else:
        raise ValueError(f"Unknown tool: {name}")


async def _write_json_line(payload: Dict[str, Any], lock: asyncio.Lock) -> None:
    """Writes exactly one complete JSON-RPC line to stdout, atomically.

    The lock is held across the write AND the flush so two responses that
    finish at the same time can never interleave mid-line and corrupt the
    stream. A partially written line would break the client's parser for
    every message that follows, so this is the one place that must not be
    "optimised" into an unlocked write.
    """
    out_bytes = (json.dumps(payload) + "\n").encode("utf-8")
    try:
        async with lock:
            sys.stdout.buffer.write(out_bytes)
            sys.stdout.buffer.flush()
    except BrokenPipeError:
        # The client hung up. Nothing left to write to.
        logger.warning("stdout closed by the client - dropping response")


async def _handle_mcp_request(req: Dict[str, Any], write_lock: asyncio.Lock) -> None:
    """Handles one JSON-RPC request and writes its response.

    Runs as its own task so that a slow tool call never blocks the reader.
    Responses are written as they complete, which means they may be emitted
    OUT OF ORDER relative to the requests that produced them. That is legal
    JSON-RPC: a client matches every response to its request by ``id``, so
    ordering is not part of the contract.
    """
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    # A request without an id is a NOTIFICATION. JSON-RPC 2.0 says the
    # server MUST NOT reply to a notification, so a request that carries no
    # id is executed but never answered.
    is_notification = req_id is None

    response: Optional[Dict[str, Any]] = None

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
        # Notification only, no reply required.
        return
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
        tool_args = params.get("arguments") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}
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
            logger.exception("Error executing tool %s", tool_name)
            # A tool that fails at execution time must return a RESULT
            # with isError=true, not a transport-level JSON-RPC error.
            # The model can read a tool result and react to it; a
            # transport error is invisible to it and it typically retries
            # or gives up. The raw exception text also leaked raw SQL
            # into the transcript.
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{
                        "type": "text",
                        "text": (
                            f"Tool '{tool_name}' failed: {type(tool_err).__name__}. "
                            "Check the arguments and the system state with "
                            "`leadforge_get_stats` / `leadforge_search_leads`, then "
                            "retry with corrected arguments."
                        ),
                    }],
                    "isError": True,
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

    if response is None or is_notification:
        # Notifications never get a response.
        return

    await _write_json_line(response, write_lock)


async def run_mcp_server():
    """Runs the Model Context Protocol stdio loop.

    Requests are handled CONCURRENTLY. The reader keeps consuming stdin
    while the tool calls are still running, so a five-minute scrape no
    longer blocks every other request behind it - and each request gets
    its own task, so one slow tool call cannot stall the others either.

    Responses are written as they complete and may therefore arrive OUT OF
    ORDER relative to the requests that produced them. JSON-RPC matches
    responses to requests by ``id``, so out-of-order delivery is legal and
    is what makes concurrency possible.

    The loop exits cleanly on EOF (stdin closed) and on Ctrl-C.
    """
    logger.info("Starting LeadForge MCP stdio server...")

    # The MCP server talks to the database directly and must be able to
    # survive a schema change on its own. It used to depend on the API
    # process having started first.
    await ensure_schema()

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    # Serialises stdout writes so two responses that finish at the same
    # time can never interleave mid-line.
    write_lock = asyncio.Lock()

    # Strong references to the in-flight request tasks. Python only keeps
    # weak references to running asyncio tasks, so without this a task can
    # be garbage-collected mid-flight and the client never gets a reply.
    inflight: set = set()

    try:
        while True:
            line = await reader.readline()
            if not line:
                # EOF: the client closed stdin, the session is over.
                break

            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                req = json.loads(line_str)
            except Exception as parse_err:
                logger.error(f"JSON decode error: {parse_err}")
                # JSON-RPC requires a Parse error response with a null id.
                await _write_json_line({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: invalid JSON"},
                }, write_lock)
                continue

            if not isinstance(req, dict):
                await _write_json_line({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request: expected a JSON object"},
                }, write_lock)
                continue

            # Hand the request to its own task and go straight back to
            # reading. The task awaits the whole tool call on its own.
            task = asyncio.ensure_future(_handle_mcp_request(req, write_lock))
            inflight.add(task)
            task.add_done_callback(inflight.discard)

    except asyncio.CancelledError:
        # Ctrl-C (or a parent shutting us down): stop the world promptly.
        for t in list(inflight):
            t.cancel()
        if inflight:
            await asyncio.gather(*list(inflight), return_exceptions=True)
        raise

    # EOF: let the requests that are already running write their response
    # before the process goes away, then cancel the stragglers so the
    # server cannot hang on a long tool call forever.
    if inflight:
        logger.info("stdin closed - draining %d in-flight request(s)", len(inflight))
        pending = set(inflight)
        _, still_pending = await asyncio.wait(
            list(pending), timeout=_SHUTDOWN_GRACE_SECONDS
        )
        for t in still_pending:
            t.cancel()
        if still_pending:
            await asyncio.gather(*list(still_pending), return_exceptions=True)

    logger.info("LeadForge MCP stdio server stopped.")


def main():
    try:
        asyncio.run(run_mcp_server())
    except KeyboardInterrupt:
        # Ctrl-C: exit quietly, without a traceback.
        logger.info("LeadForge MCP server interrupted - shutting down")
        sys.exit(130)


if __name__ == "__main__":
    main()
