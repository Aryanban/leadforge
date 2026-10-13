import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional, Dict, Any, Tuple
import logging
import asyncio
import random
import re
from datetime import datetime
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_maker
from app.models.mailbox import Mailbox
from app.models.contact import Contact
from app.models.business import Business
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep
from app.models.send import Send
from app.campaigns.bounces import classify_bounce, HARD, SOFT
from app.campaigns.suppression import is_suppressed, add_suppression
from app.campaigns.warmup import (
    mailbox_age_days, ramp_limit, mailbox_health, is_mailbox_usable,
    rolling_24h_count, recent_outcomes,
)

logger = logging.getLogger(__name__)

def interpolate_template(text: str, data: Dict[str, str]) -> str:
    """Replaces {{variable}} tags in subject/body with lead data."""
    if not text:
        return ""
    result = text
    for key, val in data.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(val or ""))
    return result


def _domain_from_email(email: str) -> str:
    """Returns the domain part of an address, for Message-ID generation."""
    return (email or "").rsplit("@", 1)[-1].lower() or "localhost"


def jitter_seconds() -> float:
    """Randomized inter-send delay in seconds, clamped to the configured band.

    A fixed sleep betrays blast software and gets the mailbox throttled by ISP
    rate-limit heuristics; humans do not send on a metronome. Each send waits a
    random duration in [SEND_JITTER_MIN_SECONDS, SEND_JITTER_MAX_SECONDS].
    """
    lo = float(getattr(settings, "SEND_JITTER_MIN_SECONDS", 20))
    hi = float(getattr(settings, "SEND_JITTER_MAX_SECONDS", 60))
    if hi < lo:
        lo, hi = hi, lo
    if lo <= 0 and hi <= 0:
        return 0.0
    return random.uniform(lo, hi)



def resolve_city(business: Optional[Business]) -> str:
    """Best-effort human-readable town for a lead.

    Order of preference:
      1. An explicit `city` already stored in ``extra_data`` (set by sources
         that know their city, e.g. the IndiaMART/JustDial parsers).
      2. ``extract_city()`` applied to the street address.
      3. The ICP area the business was discovered under.
      4. A neutral fallback - never a hardcoded city.
    """
    if business is None:
        return "your area"

    extra = business.extra_data or {}
    explicit = extra.get("city") or extra.get("area") or extra.get("locality")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    try:
        from app.sources.http_utils import extract_city
        derived = extract_city(business.address)
    except Exception:  # pragma: no cover - defensive, never break a send
        derived = None
    if derived:
        return derived

    icp = getattr(business, "icp_profile", None)
    if icp is not None and getattr(icp, "area", None):
        return str(icp.area).strip()

    return "your area"


def test_smtp_connection(host: str, port: int, user: str, password: str) -> Tuple[bool, str]:
    """Tests credentials against remote SMTP server using TLS or SSL."""
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(user, password)
        server.quit()
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def send_single_email(
    mailbox: Mailbox,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    send_id: Optional[int] = None,
    contact_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """Sends an email via the provided Mailbox's SMTP configuration."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        from_name = f"{mailbox.first_name} {mailbox.last_name}".strip() if mailbox.first_name else mailbox.email
        msg["From"] = f"{from_name} <{mailbox.email}>"
        msg["To"] = to_email
        # Date & Message-ID headers. Missing or malformed values are a spam
        # signal at Gmail/Outlook/M365 — the MTA otherwise injects a
        # local-time Date that can predate the message, which bulk filters flag.
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=_domain_from_email(mailbox.email))

        tracking_base = settings.TRACKING_DOMAIN.rstrip("/")

        # Inject List-Unsubscribe headers.
        # RFC 8058 one-click POST is mandatory for bulk senders at Gmail and
        # Yahoo (Feb 2024+). Without `List-Unsubscribe-Post` the unsubscribe
        # link is not rendered in the Gmail UI and the sender is penalised.
        if contact_id:
            unsub_url = f"{tracking_base}/api/v1/campaigns/tracker/unsubscribe/{contact_id}"
            msg["List-Unsubscribe"] = f"<{unsub_url}>, <mailto:{mailbox.email}?subject=unsubscribe>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        # Open-tracking pixel — GATED OFF by default.
        # A 1x1 remote image fetched from a third-party tracking domain is a
        # commercial-newsletter signal at Gmail/Outlook/Yahoo (2026): it routes
        # the message straight to Promotions/Spam. For cold outreach we default
        # this OFF (OPEN_TRACKING_ENABLED=False) — you trade open-rate telemetry
        # for the only cold metric that matters, the Primary inbox. Reply
        # tracking (via a real reply to the mailbox) still works regardless.
        pixel_tag = ""
        if send_id and getattr(settings, "OPEN_TRACKING_ENABLED", False):
            pixel_url = f"{tracking_base}/api/v1/campaigns/tracker/open/{send_id}"
            pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none;" alt="" />'

        unsub_footer_html = ""
        unsub_footer_text = ""
        if contact_id:
            unsub_footer_html = f'<p style="margin-top:24px;font-size:11px;color:#888;">To stop receiving these emails, <a href="{unsub_url}">unsubscribe here</a>.</p>'
            unsub_footer_text = f"\n\nTo stop receiving these emails: {unsub_url}"

        # Plain text
        full_text = body_text + unsub_footer_text
        msg.attach(MIMEText(full_text, "plain", "utf-8"))

        # HTML
        if body_html:
            if "</body>" in body_html:
                full_html = body_html.replace("</body>", f"{pixel_tag}{unsub_footer_html}</body>")
            else:
                full_html = f"<html><body>{body_html}{pixel_tag}{unsub_footer_html}</body></html>"
            msg.attach(MIMEText(full_html, "html", "utf-8"))
        else:
            simple_html = f"<html><body style='font-family:sans-serif;line-height:1.5;'>{body_text.replace(chr(10), '<br>')}{pixel_tag}{unsub_footer_html}</body></html>"
            msg.attach(MIMEText(simple_html, "html", "utf-8"))

        # Send via SMTP
        if mailbox.smtp_port == 465:
            server = smtplib.SMTP_SSL(mailbox.smtp_host, mailbox.smtp_port, timeout=12)
        else:
            server = smtplib.SMTP(mailbox.smtp_host, mailbox.smtp_port, timeout=12)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(mailbox.email, mailbox.password)
        server.sendmail(mailbox.email, to_email, msg.as_string())
        server.quit()
        return True, ""

    except Exception as e:
        logger.error(f"Error sending email to {to_email} via {mailbox.email}: {e}")
        return False, str(e)


from app.enricher.ai_icebreaker import generate_ai_icebreaker

async def execute_campaign_step(campaign_id: int, max_sends: int = 50) -> Dict[str, Any]:
    """
    Orchestrates the dispatch of a multi-step campaign sequence:
    1. Fetches all configured steps ordered by step_number
    2. Identifies contacts needing Step 1, or Step N+1 whose delay_days have elapsed
    3. Auto-suppresses bounced, unsubscribed, or replied contacts
    4. Automatically injects AI icebreakers and personalized business hooks
    5. Rotates across active mailboxes respecting daily limits
    6. Automatically marks recipient as bounced on SMTP rejection (550/554)
    """
    sent_count = 0
    failed_count = 0
    bounced_count = 0

    # Single timestamp for the whole run. The mailbox warmup/ramp gate below
    # (mailbox_age_days / rolling_24h_count) and the per-step delay math both
    # read this, so it must be captured once, up front - not partway through.
    now = datetime.utcnow()
    async with async_session_maker() as db:
        campaign = await db.get(Campaign, campaign_id)
        if not campaign or campaign.status != CampaignStatus.ACTIVE.value:
            return {"error": "Campaign not found or not active"}

        # Get all campaign steps
        stmt = (
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign_id)
            .order_by(CampaignStep.step_number.asc())
        )
        res = await db.execute(stmt)
        steps = res.scalars().all()
        if not steps:
            return {"error": "No steps configured for this campaign"}

        steps_by_number = {s.step_number: s for s in steps}
        step_ids_to_step = {s.id: s for s in steps}

        # Get available mailboxes, then apply the warmup/health/rolling gates.
        # `sent_today < daily_limit` is only a fast pre-filter: the rolling
        # 24h count over real Send timestamps is authoritative, a new mailbox
        # ramps 10 -> limit over RAMP_DAYS, and a sick mailbox is held out
        # until reviewed. Aged healthy mailboxes rotate first so fresh ones
        # build reputation slowly - this is what keeps Gmail bulk-foldering
        # at bay for new sending domains.
        m_stmt = select(Mailbox).where(Mailbox.is_active == True, Mailbox.sent_today < Mailbox.daily_limit)
        m_res = await db.execute(m_stmt)
        candidates_mb = list(m_res.scalars().all())

        mailboxes = []
        for mb in candidates_mb:
            if getattr(mb, "health_paused", False):
                logger.info("mailbox %s held out: health pause until review", mb.email)
                continue
            age = mailbox_age_days(getattr(mb, "created_at", None), now)
            cap = ramp_limit(mb.daily_limit or 50, age)
            used = await rolling_24h_count(db, mb.id, now)
            if used >= cap:
                continue
            bounced, failed, sent = await recent_outcomes(db, mb.id)
            health = mailbox_health(bounced, failed, sent)
            mb.health_score = health
            usable, reason = is_mailbox_usable(health, age)
            if not usable:
                mb.health_paused = True
                logger.warning("mailbox %s auto-paused: health %.3f", mb.email, health)
                continue
            mailboxes.append((0 if reason == "ready" else 1, mb))

        if candidates_mb:
            await db.commit()  # persist refreshed health scores / auto-pauses

        mailboxes = [mb for _, mb in sorted(mailboxes, key=lambda t: t[0])]

        if not mailboxes:
            return {"error": "No active mailboxes available with remaining daily quota"}

        # Load candidate contacts who have an email, haven't unsubscribed, and haven't bounced.
        # If this campaign has explicit targets (Apollo-style "Add to Sequence"),
        # scope to them: a campaign must never email a lead the operator didn't
        # pick. An empty target set keeps the legacy all-eligible behaviour so
        # campaigns created before targeting existed still run.
        from app.models.campaign_step import CampaignTarget
        target_stmt = select(CampaignTarget.contact_id).where(
            CampaignTarget.campaign_id == campaign_id)
        target_res = await db.execute(target_stmt)
        target_ids = {row[0] for row in target_res.all()}

        c_stmt = (
            select(Contact, Business)
            .join(Business, Contact.business_id == Business.id, isouter=True)
            .where(
                Contact.email.isnot(None),
                Contact.unsubscribed == False,
                Contact.verification_status != "bounced"
            )
        )
        if target_ids:
            c_stmt = c_stmt.where(Contact.id.in_(target_ids))
        c_res = await db.execute(c_stmt)
        candidates = c_res.all()

        if not candidates:
            campaign.status = CampaignStatus.COMPLETED.value
            await db.commit()
            return {"message": "No eligible contacts found", "sent": 0}

        # Retrieve all previous sends for this campaign
        sends_stmt = select(Send).where(Send.campaign_id == campaign_id)
        sends_res = await db.execute(sends_stmt)
        all_sends = sends_res.scalars().all()

        sends_by_contact: Dict[int, List[Send]] = {}
        for s in all_sends:
            sends_by_contact.setdefault(s.contact_id, []).append(s)

        queue_to_send: List[Tuple[Contact, Business, CampaignStep]] = []

        for contact, business in candidates:
            c_sends = sends_by_contact.get(contact.id, [])

            # Authoritative suppression gate (gate 3 of 4). The per-contact
            # `unsubscribed` boolean only records an unsubscribe on THIS row;
            # a bounce, complaint or "stop" reply on any campaign must block
            # the address everywhere. Check the workspace-wide table here,
            # immediately before we would open an SMTP connection.
            suppression_reason = await is_suppressed(db, contact.email)
            if suppression_reason:
                contact.unsubscribed = True
                if suppression_reason == HARD:
                    contact.verification_status = "bounced"
                    contact.is_verified = False
                logger.info(
                    "suppressing %s before queue (%s)", contact.email, suppression_reason
                )
                continue

            # If recipient already replied or bounced, skip them
            if any(s.replied for s in c_sends) or any(s.status == "bounced" for s in c_sends):
                continue

            if not c_sends:
                # Needs Step 1
                step_1 = steps_by_number.get(1)
                if step_1:
                    queue_to_send.append((contact, business, step_1))
            else:
                # Find the latest successfully sent step
                sorted_sends = sorted(
                    [s for s in c_sends if s.status == "sent" and s.sent_at],
                    key=lambda x: x.sent_at,
                    reverse=True
                )
                if not sorted_sends:
                    # Retry pending or failed
                    step_1 = steps_by_number.get(1)
                    if step_1:
                        queue_to_send.append((contact, business, step_1))
                    continue

                last_send = sorted_sends[0]
                last_step = step_ids_to_step.get(last_send.step_id)
                last_step_num = last_step.step_number if last_step else 1
                next_step_num = last_step_num + 1

                if next_step_num in steps_by_number:
                    next_step = steps_by_number[next_step_num]
                    # Check delay requirement in days
                    days_elapsed = (now - last_send.sent_at).total_seconds() / 86400.0
                    if days_elapsed >= next_step.delay_days:
                        queue_to_send.append((contact, business, next_step))

            if len(queue_to_send) >= max_sends:
                break

        if not queue_to_send:
            # Check if all active contacts have finished all steps
            campaign.status = CampaignStatus.COMPLETED.value
            await db.commit()
            return {"message": "All eligible contacts are up to date with sequence schedule", "sent": 0}

        mailbox_idx = 0

        for idx, (contact, business, step) in enumerate(queue_to_send):
            mailbox = mailboxes[mailbox_idx % len(mailboxes)]
            mailbox_idx += 1

            # Resolve the real location/category for THIS lead. Never assume
            # the campaign's city or industry - a Delhi-targeted campaign can
            # still pull in a Noida lead, and {{city}} must match the town the
            # recipient actually trades in.
            lead_city = resolve_city(business)
            lead_category = (business.industry if business and business.industry else None) or "your business"

            # Synthesize AI Icebreaker intelligence if available
            icebreaker_info = generate_ai_icebreaker(
                business_name=business.name if business else "Your Business",
                industry=lead_category,
                city=lead_city,
                rating=business.rating if business else None,
                reviews_count=business.reviews_count if business else None,
                website=business.website if business else None,
                first_name=contact.first_name
            )

            data = {
                "business_name": business.name if business else "Your Business",
                "first_name": contact.first_name or "Friend",
                "last_name": contact.last_name or "",
                "phone": contact.phone or (business.phone if business else "") or "",
                "city": lead_city,
                "category": lead_category,
                "website": business.website if business else "",
                "ai_icebreaker": icebreaker_info["ai_icebreaker"],
                "compliment": icebreaker_info["compliment"],
                "pain_point": icebreaker_info["pain_point"],
                "call_to_action": icebreaker_info["call_to_action"]
            }

            rendered_subject = interpolate_template(step.subject, data)
            rendered_body_text = interpolate_template(step.body_text, data)
            rendered_body_html = interpolate_template(step.body_html, data) if step.body_html else None

            send_record = Send(
                campaign_id=campaign_id,
                step_id=step.id,
                contact_id=contact.id,
                mailbox_id=mailbox.id,
                status="pending"
            )
            db.add(send_record)
            await db.flush()

            success, err = send_single_email(
                mailbox=mailbox,
                to_email=contact.email,
                subject=rendered_subject,
                body_text=rendered_body_text,
                body_html=rendered_body_html,
                send_id=send_record.id,
                contact_id=contact.id
            )

            # Classify the failure by SMTP semantics, not by substring
            # matching. Only a permanent (5xx recipient) bounce is recorded as
            # "bounced" and suppressed forever; a soft bounce is retried and a
            # policy block leaves the lead untouched. The old inline check
            # matched "550" anywhere in the text, which misfired on messages
            # that merely quote a code.
            bounce_reason = classify_bounce(err) if not success else None

            if success:
                send_record.status = "sent"
                send_record.sent_at = datetime.utcnow()
                mailbox.sent_today += 1
                sent_count += 1
            elif bounce_reason == HARD:
                send_record.status = "bounced"
                send_record.error_message = err
                contact.verification_status = "bounced"
                contact.is_verified = False
                await add_suppression(db, contact.email, HARD, detail=err)
                bounced_count += 1
            elif bounce_reason == SOFT:
                send_record.status = "failed"
                send_record.error_message = err
                # Transient: do not mark the lead bad. A soft suppression with
                # an expiry guards the next batch while the mailbox recovers.
                await add_suppression(db, contact.email, SOFT, detail=err)
                failed_count += 1
            else:
                # Not a recipient problem (policy block / unknown). Retry, but
                # never suppress - the address is fine, our sender is not.
                send_record.status = "failed"
                send_record.error_message = err
                failed_count += 1

            await db.commit()
            # Randomized inter-send jitter (2026 playbook Rule 5). A constant
            # delay betrays programmatic blasting and gets the mailbox
            # throttled. Skip the wait after the final queued send so the run
            # doesn't idle for a full jitter window after the last message.
            if idx < len(queue_to_send) - 1:
                await asyncio.sleep(jitter_seconds())

        return {
            "campaign_id": campaign_id,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "bounced_count": bounced_count
        }

