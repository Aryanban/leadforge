import smtplib
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from typing import Optional, Dict, Any, Tuple
import logging
import asyncio
import random
import re
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_maker
from app.models.mailbox import Mailbox
from app.models.contact import Contact
from app.models.business import Business
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep
from app.models.send import Send
from app.campaigns.bounces import classify_bounce, HARD, SOFT
from app.campaigns.suppression import is_suppressed, add_suppression, suppressed_reasons
from app.models.suppression import PERMANENT_REASONS
from app.campaigns.india_copy import localize_template
from app.sources import in_phone
from app.campaigns.warmup import (
    mailbox_age_days, ramp_limit, mailbox_health, is_mailbox_usable,
    rolling_24h_count, recent_outcomes,
)

logger = logging.getLogger(__name__)

#: IST - the operator's day. "Sent today" and the daily quota are counted on
#: the calendar day the salesperson actually lives in, not UTC.
IST = ZoneInfo("Asia/Kolkata")

#: A send is only suppressed after this many transient failures. A single
#: gateway hiccup must never delete a good lead for 30 days.
SOFT_MAX_ATTEMPTS = 3

#: Verification states that make an address undeliverable. The sender refuses
#: these outright: mailing a known-dead address is a hard bounce, and hard
#: bounces are how a sending domain gets permanently blocklisted.
UNSENDABLE_STATUSES = (
    "bounced", "invalid", "syntax_error", "gibberish", "disposable",
    "no_mx", "domain_error", "spamtrap", "abuse", "do_not_mail", "mailbox_full",
)

#: Reply categories that must NOT stop a sequence. An out-of-office
#: auto-responder is not a conversation - treating it as one silently ends
#: the follow-up chain on every lead whose owner travels.
_NON_TERMINAL_REPLIES = ("out_of_office",)

_TOKEN_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalises a datetime to timezone-aware UTC.

    SQLite hands back naive datetimes; Postgres (DateTime(timezone=True))
    hands back aware ones. Mixing the two makes ``aware - naive`` raise
    TypeError, which broke the sequence delay math on Postgres outright.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def interpolate_template(text: str, data: Dict[str, str], *, escape: bool = False,
                          fallback: str = "") -> str:
    """Replaces {{variable}} tags in subject/body with lead data.

    An unknown tag is *blanked*, never shipped literally. A stray
    ``{{frist_name}}`` used to reach the prospect verbatim, which reads as an
    obviously automated mail and poisons the sender's reputation. Unknown tags
    are logged so the operator can fix the template.
    """
    if not text:
        return ""
    missing: list[str] = []

    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in data:
            missing.append(key)
            return fallback
        value = str(data.get(key) or "")
        return html.escape(value, quote=True) if escape else value

    rendered = _TOKEN_RE.sub(_sub, text)
    if missing:
        logger.warning(
            "template references unknown token(s) %s - rendered blank", sorted(set(missing))
        )
    return rendered



def _rewrite_links_for_tracking(body: str, tracking_base: str, send_id: Optional[int]) -> str:
    """Rewrites ``<a href="...">`` links to the click-tracking redirect.

    Click tracking did not exist: there was no ``/click`` route, the
    ``Send.clicked`` column was never written, and the warm-WhatsApp handoff
    panel (which needs three opens or one click) could therefore never
    populate. Open tracking is deliberately off by default - a tracking pixel
    is a primary-inbox killer - which left click tracking as the only
    engagement signal available.

    The unsubscribe link is never rewritten: it must keep working even if
    tracking is misconfigured, and it is appended after this runs anyway.
    """
    if not send_id or not body:
        return body
    if "http" not in body:
        return body

    def _replace(match: "re.Match[str]") -> str:
        href = match.group(2)
        if not href.startswith("http"):
            return match.group(0)
        if "unsubscribe" in href or "tracker/" in href:
            return match.group(0)
        tracker = f"{tracking_base.rstrip('/')}/api/v1/campaigns/tracker/click/{send_id}"
        return f'{match.group(1)}"{tracker}?u={quote(href, safe="")}"'

    return re.sub(r'(href\s*=\s*")([^"]+)(")', _replace, body)


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
    message_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """Sends an email via the provided Mailbox's SMTP configuration.

    message_id: pre-generated RFC 5322 Message-ID (the caller stores it on the
    Send row so the IMAP reply poller can attribute inbound replies). When
    omitted a fresh one is generated.
    """
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
        msg["Message-ID"] = message_id or make_msgid(domain=_domain_from_email(mailbox.email))

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

    except smtplib.SMTPSenderRefused as e:
        # OUR problem, not the recipient's. A rejected MAIL FROM (SPF
        # misalignment, a blocked envelope sender, a policy gate) says nothing
        # about the address we were trying to reach. Tagging it keeps the
        # bounce classifier from suppressing the entire lead database.
        logger.error("Sender rejected by %s for %s: %s", mailbox.smtp_host, to_email, e)
        return False, f"sender_rejected:{e.smtp_code}:{e.smtp_error}"
    except smtplib.SMTPRecipientsRefused as e:
        # A genuine recipient refusal. smtplib gives us the per-recipient
        # reply code, which is exactly what the classifier needs. The code is
        # emitted FIRST so the classifier's code scanner cannot accidentally
        # match digits inside the address itself.
        details = "; ".join(
            f"{code} {msg}" for _addr, (code, msg) in (e.recipients or {}).items()
        )
        logger.error("Recipient refused by %s for %s: %s", mailbox.smtp_host, to_email, details)
        return False, f"recipient_refused:{details}"
    except smtplib.SMTPDataError as e:
        # Message content rejected at DATA time - our problem, not theirs.
        logger.error("Data rejected by %s for %s: %s", mailbox.smtp_host, to_email, e)
        return False, f"data_rejected:{e.smtp_code}:{e.smtp_error}"
    except Exception as e:
        logger.error(f"Error sending email to {to_email} via {mailbox.email}: {e}")
        return False, str(e)


async def send_single_email_async(*args: Any, **kwargs: Any) -> Tuple[bool, str]:
    """Runs the blocking SMTP handshake off the event loop.

    ``send_single_email`` performs a TCP connect, a TLS handshake and an
    authentication round-trip - seconds of blocking I/O. Called directly from
    an ``async def`` it freezes the whole API (and the in-process reply
    poller) for the duration of every send.
    """
    return await asyncio.to_thread(send_single_email, *args, **kwargs)


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
    # Timezone-aware: SQLite returns naive datetimes and Postgres returns
    # aware ones, and mixing the two made the delay subtraction raise
    # TypeError on Postgres outright.
    now = datetime.now(timezone.utc)
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
        # The rolling 24h count over real Send timestamps is authoritative: a
        # new mailbox ramps 10 -> limit over RAMP_DAYS, and a sick mailbox is
        # held out until reviewed. Aged healthy mailboxes rotate first so
        # fresh ones build reputation slowly - this is what keeps Gmail
        # bulk-foldering at bay for new sending domains.
        #
        # NB: the mailbox's own ``sent_today`` counter is NOT used as a filter.
        # It used to be, and because it was never reset it silently became a
        # *lifetime* cap: after `daily_limit` sends the mailbox was excluded
        # forever and the whole outreach engine stopped after 50 emails.
        m_stmt = select(Mailbox).where(Mailbox.is_active == True)
        m_res = await db.execute(m_stmt)
        candidates_mb = list(m_res.scalars().all())

        # Reset the per-day counters for any mailbox whose last send was on a
        # previous IST calendar day, so the dashboard's "sent today" is honest
        # and the daily limit means *per day*.
        today = now.astimezone(IST).strftime("%Y-%m-%d")
        for mb in candidates_mb:
            if getattr(mb, "sent_today_date", None) != today:
                mb.sent_today = 0
                mb.sent_today_date = today

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

        # Load candidate contacts who have an email, haven't unsubscribed, and
        # are actually deliverable.
        #
        # The verification gate used to exclude exactly one status ("bounced"),
        # which meant `invalid`, `syntax_error`, `gibberish`, `disposable` and
        # `no_mx` addresses were all mailed. The verifier goes to real lengths
        # never to report a dead address as valid, and then that verdict was
        # thrown away one file away - so a list of scraped Indian SMB addresses
        # (where ~30% are junk) went out with a ~30% hard-bounce rate against
        # a 5% bulk-sender ceiling.
        #
        # Un-enriched contacts (status NULL or "pending") stay eligible: we
        # cannot know they are bad, and refusing them would silently disable
        # outreach entirely.
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
                or_(
                    Contact.verification_status.is_(None),
                    Contact.verification_status.notin_(UNSENDABLE_STATUSES),
                ),
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
        #: Contacts still inside the sequence whose next step is waiting on a
        #: delay. The old code could not tell "everyone finished" apart from
        #: "everyone is waiting", so a campaign was marked COMPLETED the
        #: moment it was launched and the dashboard showed in-flight
        #: sequences as done.
        pending_delays = 0

        # The authoritative suppression gate (gate 3 of 4). The per-contact
        # `unsubscribed` boolean only records an unsubscribe on THIS row; a
        # bounce, complaint or "stop" reply on any campaign must block the
        # address everywhere.
        #
        # The whole candidate set is checked in ONE query. It used to be
        # `await is_suppressed(db, contact.email)` inside the loop - one
        # round-trip per candidate, so a 500-target campaign spent 500
        # queries deciding who not to email.
        candidate_emails = [c.email for c, _b in candidates if c.email]
        suppression_reasons = await suppressed_reasons(db, candidate_emails)

        for contact, business in candidates:
            c_sends = sends_by_contact.get(contact.id, [])

            suppression_reason = suppression_reasons.get((contact.email or "").lower())
            if suppression_reason:
                # Only a genuine opt-out flips the per-contact flag. A soft
                # bounce has a 30-day expiry, and setting the flag for it made
                # a transient gateway failure remove the lead permanently.
                if suppression_reason in ("unsubscribed", "replied_stop", "complaint", "manual"):
                    contact.unsubscribed = True
                if suppression_reason == HARD:
                    contact.verification_status = "bounced"
                    contact.is_verified = False
                logger.info(
                    "suppressing %s before queue (%s)", contact.email, suppression_reason
                )
                continue

            # Stop on a real reply. An out-of-office auto-responder is not a
            # conversation - ending the follow-up chain on it silently cost us
            # the second and third touches on every lead whose owner travels.
            def _is_terminal(send: Send) -> bool:
                if send.status == "bounced":
                    return True
                if not send.replied:
                    return False
                category = (send.reply_category or "").lower()
                return category not in _NON_TERMINAL_REPLIES

            if any(_is_terminal(s) for s in c_sends):
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
                    last_sent_at = _as_utc(last_send.sent_at) or now
                    days_elapsed = (now - last_sent_at).total_seconds() / 86400.0
                    if days_elapsed >= (next_step.delay_days or 0):
                        queue_to_send.append((contact, business, next_step))
                    else:
                        # Still waiting on the step delay - the sequence is
                        # alive, it just is not due yet.
                        pending_delays += 1
                else:
                    # No further step configured: this contact is finished.
                    pass

            if len(queue_to_send) >= max_sends:
                break

        if not queue_to_send:
            if pending_delays > 0:
                # The sequence is mid-flight and simply waiting for the next
                # step's delay to elapse. Leave it ACTIVE so the scheduler
                # picks it up when it becomes due.
                logger.info(
                    "campaign %s: %d contact(s) waiting on a step delay", campaign_id, pending_delays
                )
                await db.commit()
                return {
                    "message": f"{pending_delays} contact(s) are waiting on the next step delay",
                    "sent": 0,
                    "pending": pending_delays,
                }
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

            # India localisation. `localize_template` only substitutes
            # `{{festival_line}}` (and empties it outside a festival window),
            # so it is safe to apply automatically. It was never called, so a
            # template using that token shipped the literal braces to the
            # prospect.
            body_text = localize_template(step.body_text or "", city=lead_city)
            body_html = localize_template(step.body_html, city=lead_city) if step.body_html else None

            # Channel routing. `preferred_channel` is computed at enrichment
            # time from the line type - whatsapp / call / email - and was
            # never read by the sender, so the headline India differentiator
            # (Indian SMB owners answer WhatsApp, and only a mobile can be
            # reached on it) changed nothing. A WhatsApp-reachable lead now
            # gets a `{{whatsapp_link}}` token and a CTA that points there.
            channel = (getattr(contact, "preferred_channel", None) or "").lower()
            if not channel:
                channel = in_phone.preferred_channel(
                    contact.phone or (business.phone if business else None)
                )
            wa_digits = "".join(filter(str.isdigit, contact.phone or ""))
            if not wa_digits and business is not None:
                wa_digits = "".join(filter(str.isdigit, business.phone or ""))
            whatsapp_link = f"https://wa.me/{wa_digits}" if wa_digits else None

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
                "call_to_action": icebreaker_info["call_to_action"],
                # India channel tokens.
                "channel": channel,
                "whatsapp_link": whatsapp_link or "",
            }
            if channel == "whatsapp" and whatsapp_link:
                # A WhatsApp-first lead should be invited to WhatsApp, not
                # asked to reply to an inbox they do not monitor.
                data["call_to_action"] = (
                    f"Quick question - WhatsApp is easier? {whatsapp_link}"
                )
            elif channel == "call":
                data["call_to_action"] = (
                    f"Would a 4-minute call this week work? {data['phone']}"
                )

            rendered_subject = interpolate_template(step.subject, data)
            # A/B subject test. While undecided, split evenly by contact-id
            # parity so each recipient always sees the same variant; once a
            # winner is declared the loser stops sending. Open rate is NOT the
            # metric here — opens require the (deliverability-killing) tracking
            # pixel, so cold A/B is decided on replies, the only signal that
            # survives with open tracking off.
            use_variant = None
            if getattr(step, "subject_b", None) and not getattr(step, "variant_winner", None):
                use_variant = "b" if (contact.id or 0) % 2 == 1 else "a"
            elif getattr(step, "subject_b", None) and getattr(step, "variant_winner", None) == "b":
                use_variant = "b"
            if use_variant == "b":
                rendered_subject = interpolate_template(step.subject_b, data)
            rendered_body_text = interpolate_template(body_text, data)
            # HTML body: escape interpolated values so a business named
            # "Suresh & Sons <Deals>" cannot corrupt the markup.
            rendered_body_html = (
                interpolate_template(body_html, data, escape=True)
                if body_html else None
            )

            outbox_message_id = make_msgid(domain=_domain_from_email(mailbox.email))
            send_record = Send(
                campaign_id=campaign_id,
                step_id=step.id,
                contact_id=contact.id,
                mailbox_id=mailbox.id,
                status="sending",
                message_id=outbox_message_id,
                variant_used=use_variant,
                attempt=1,
            )
            db.add(send_record)
            # Commit the intent to send BEFORE the SMTP call. If the process
            # dies mid-flight the row survives as "sending" and the reaper can
            # reconcile it; previously the row was only flushed, so a crash
            # between delivery and commit left the prospect with a delivered
            # email and no record - and the next run mailed them again.
            await db.commit()

            # Now that the send row exists we know its id, so links can be
            # rewritten to the click tracker.
            if rendered_body_html:
                rendered_body_html = _rewrite_links_for_tracking(
                    rendered_body_html,
                    settings.TRACKING_DOMAIN.rstrip("/"),
                    send_record.id,
                )

            success, err = await send_single_email_async(
                mailbox=mailbox,
                to_email=contact.email,
                subject=rendered_subject,
                body_text=rendered_body_text,
                body_html=rendered_body_html,
                send_id=send_record.id,
                contact_id=contact.id,
                message_id=outbox_message_id
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
                send_record.sent_at = datetime.now(timezone.utc)
                mailbox.sent_today = (mailbox.sent_today or 0) + 1
                mailbox.sent_today_date = today
                sent_count += 1
            elif bounce_reason == HARD:
                send_record.status = "bounced"
                send_record.error_message = err
                send_record.bounced = True
                contact.verification_status = "bounced"
                contact.is_verified = False
                await add_suppression(db, contact.email, HARD, detail=err)
                bounced_count += 1
            elif bounce_reason == SOFT:
                send_record.status = "failed"
                send_record.error_message = err
                # Transient: do not mark the lead bad, and do not suppress it
                # yet either. A soft suppression with an expiry guards the
                # next batch while the mailbox recovers - but only once the
                # retry budget is exhausted. One gateway hiccup used to park
                # a perfectly good lead for 30 days.
                prior_attempts = sum(
                    1 for s in sends_by_contact.get(contact.id, [])
                    if s.status == "failed" and s.step_id == step.id
                )
                if prior_attempts + 1 >= SOFT_MAX_ATTEMPTS:
                    await add_suppression(db, contact.email, SOFT, detail=err)
                failed_count += 1
            else:
                # Not a recipient problem (policy block / unknown / our own
                # sender misconfiguration). Retry, but never suppress - the
                # address is fine, our sender is not.
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

        # Finalise the A/B winner here, not only in the stats endpoint.
        #
        # The winner used to be declared as a side effect of somebody
        # opening the sequence-detail page. If nobody looked, the test ran
        # to the end of the campaign with both variants still live and no
        # verdict - which is exactly when you want the answer.
        ab_winner = await _finalise_ab_winner(db, campaign_id)

        return {
            "campaign_id": campaign_id,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "bounced_count": bounced_count,
            "ab_winner": ab_winner,
        }


async def _finalise_ab_winner(db: AsyncSession, campaign_id: int) -> Optional[str]:
    """Declares the A/B subject winner for a campaign, if one is due.

    Uses the same significance test as the stats endpoint, so both agree.
    Returns the winner ("a"/"b") or None.
    """
    from app.api.campaigns import AB_POSITIVE_REPLIES, decide_ab_winner

    steps = (await db.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == campaign_id)
    )).scalars().all()
    ab_steps = [s for s in steps if getattr(s, "subject_b", None)]
    if not ab_steps:
        return None

    sends = (await db.execute(
        select(Send).where(Send.campaign_id == campaign_id, Send.status == "sent")
    )).scalars().all()

    by_step: Dict[int, List[Any]] = {}
    for s in sends:
        by_step.setdefault(s.step_id, []).append(s)

    declared: Optional[str] = None
    changed = False
    for step in ab_steps:
        if getattr(step, "variant_winner", None):
            declared = declared or step.variant_winner
            continue
        rows = by_step.get(step.id, [])
        a = [s for s in rows if (getattr(s, "variant_used", None) or "a") == "a"]
        b = [s for s in rows if getattr(s, "variant_used", None) == "b"]
        a_rep = sum(1 for s in a if (getattr(s, "reply_category", "") or "") in AB_POSITIVE_REPLIES)
        b_rep = sum(1 for s in b if (getattr(s, "reply_category", "") or "") in AB_POSITIVE_REPLIES)
        winner = decide_ab_winner(len(a), a_rep, len(b), b_rep)
        if winner:
            step.variant_winner = winner
            declared = declared or winner
            changed = True
            logger.info(
                "campaign %s step %s: A/B winner is %s (%d vs %d positive replies)",
                campaign_id, step.id, winner, a_rep, b_rep,
            )
    if changed:
        await db.commit()
    return declared

