import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple
import logging
import asyncio
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

        tracking_base = settings.TRACKING_DOMAIN.rstrip("/")

        # Inject List-Unsubscribe headers
        if contact_id:
            unsub_url = f"{tracking_base}/api/v1/campaigns/tracker/unsubscribe/{contact_id}"
            msg["List-Unsubscribe"] = f"<{unsub_url}>"

        # Inject open tracking pixel and unsubscribe link
        pixel_tag = ""
        if send_id:
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

        # Get available mailboxes
        m_stmt = select(Mailbox).where(Mailbox.is_active == True, Mailbox.sent_today < Mailbox.daily_limit)
        m_res = await db.execute(m_stmt)
        mailboxes = m_res.scalars().all()

        if not mailboxes:
            return {"error": "No active mailboxes available with remaining daily quota"}

        # Load candidate contacts who have an email, haven't unsubscribed, and haven't bounced
        c_stmt = (
            select(Contact, Business)
            .join(Business, Contact.business_id == Business.id, isouter=True)
            .where(
                Contact.email.isnot(None),
                Contact.unsubscribed == False,
                Contact.verification_status != "bounced"
            )
        )
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

        now = datetime.utcnow()
        queue_to_send: List[Tuple[Contact, Business, CampaignStep]] = []

        for contact, business in candidates:
            c_sends = sends_by_contact.get(contact.id, [])

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

        for contact, business, step in queue_to_send:
            mailbox = mailboxes[mailbox_idx % len(mailboxes)]
            mailbox_idx += 1

            # Synthesize AI Icebreaker intelligence if available
            icebreaker_info = generate_ai_icebreaker(
                business_name=business.name if business else "Your Business",
                industry=business.industry if business else "General",
                city="Delhi NCR",
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
                "city": "Delhi NCR",
                "category": business.industry if business else "Real Estate",
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

            # Detect bounce codes in error message
            is_bounced = any(code in (err or "").lower() for code in ["550", "554", "user unknown", "mailbox unavailable", "recipient rejected", "no such user"])

            if success:
                send_record.status = "sent"
                send_record.sent_at = datetime.utcnow()
                mailbox.sent_today += 1
                sent_count += 1
            elif is_bounced:
                send_record.status = "bounced"
                send_record.error_message = err
                contact.verification_status = "bounced"
                contact.is_verified = False
                bounced_count += 1
            else:
                send_record.status = "failed"
                send_record.error_message = err
                failed_count += 1

            await db.commit()
            await asyncio.sleep(settings.DEFAULT_DELAY_SECONDS)

        return {
            "campaign_id": campaign_id,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "bounced_count": bounced_count
        }

