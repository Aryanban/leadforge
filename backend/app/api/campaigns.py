from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep, CampaignTarget
from app.models.business import Business
from app.models.send import Send
from app.models.contact import Contact
from app.campaigns.sender import execute_campaign_step, interpolate_template

router = APIRouter()

class StepCreate(BaseModel):
    subject: str
    body_text: str
    body_html: Optional[str] = None
    delay_days: int = 0

class CampaignCreate(BaseModel):
    name: str
    steps: List[StepCreate]
    #: Optional explicit recipients — Apollo-style "select leads → Add to Sequence".
    contact_ids: Optional[List[int]] = None

class PreviewRequest(BaseModel):
    subject: str
    body: str
    sample_data: Optional[Dict[str, str]] = None


class TargetAdd(BaseModel):
    contact_ids: List[int] = []

@router.get("")
@router.get("/")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    stmt = select(Campaign).order_by(Campaign.created_at.desc())
    res = await db.execute(stmt)
    campaigns = res.scalars().all()

    result = []
    for c in campaigns:
        # Aggregate send stats
        sends_stmt = select(
            func.count(Send.id),
            func.count(Send.id).filter(Send.status == "sent"),
            func.count(Send.id).filter(Send.opened == True),
            func.count(Send.id).filter(Send.replied == True)
        ).where(Send.campaign_id == c.id)
        
        s_res = await db.execute(sends_stmt)
        total_sends, sent_count, opened_count, replied_count = s_res.one()

        open_rate = round((opened_count / sent_count * 100), 1) if sent_count > 0 else 0.0
        reply_rate = round((replied_count / sent_count * 100), 1) if sent_count > 0 else 0.0

        # Explicit recipients (Apollo "prospects") plus total steps, so the UI
        # can render "N prospects · M steps" without a second round-trip.
        target_count = (await db.execute(
            select(func.count(CampaignTarget.id)).where(CampaignTarget.campaign_id == c.id)
        )).scalar() or 0
        step_count = (await db.execute(
            select(func.count(CampaignStep.id)).where(CampaignStep.campaign_id == c.id)
        )).scalar() or 0

        result.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "total_targets": total_sends,
            "contacts_selected": target_count,
            "step_count": step_count,
            "sent_count": sent_count,
            "opened_count": opened_count,
            "open_rate": open_rate,
            "replied_count": replied_count,
            "reply_rate": reply_rate,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })

    return result


@router.post("/")
async def create_campaign(req: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(
        name=req.name,
        status=CampaignStatus.DRAFT.value
    )
    db.add(campaign)
    await db.flush()

    for idx, step_data in enumerate(req.steps):
        step = CampaignStep(
            campaign_id=campaign.id,
            step_number=idx + 1,
            subject=step_data.subject,
            body_text=step_data.body_text,
            body_html=step_data.body_html,
            delay_days=step_data.delay_days
        )
        db.add(step)

    # Attach the explicitly selected recipients, if any.
    added_targets = 0
    for cid in dict.fromkeys(req.contact_ids or []):
        db.add(CampaignTarget(campaign_id=campaign.id, contact_id=cid))
        added_targets += 1

    await db.commit()
    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "steps": len(req.steps),
        "targets": added_targets,
    }


@router.post("/{campaign_id}/targets")
async def add_campaign_targets(
    campaign_id: int,
    req: "TargetAdd",
    db: AsyncSession = Depends(get_db),
):
    """Adds contacts to a campaign (the bulk "Add to Sequence" action).

    Idempotent: re-adding an existing target is a no-op, so the UI can call
    this on a selection without tracking what was already there.
    """
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    existing_stmt = select(CampaignTarget.contact_id).where(
        CampaignTarget.campaign_id == campaign_id)
    existing = {row[0] for row in (await db.execute(existing_stmt)).all()}

    added = 0
    for cid in dict.fromkeys(req.contact_ids or []):
        if cid in existing:
            continue
        db.add(CampaignTarget(campaign_id=campaign_id, contact_id=cid))
        added += 1
    await db.commit()

    total_stmt = select(func.count(CampaignTarget.id)).where(
        CampaignTarget.campaign_id == campaign_id)
    total = (await db.execute(total_stmt)).scalar() or 0
    return {"campaign_id": campaign_id, "added": added, "total_targets": total}


@router.get("/{campaign_id}/targets")
async def list_campaign_targets(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """Lists a campaign's explicitly selected recipients."""
    stmt = (
        select(Contact, Business)
        .join(Business, Contact.business_id == Business.id, isouter=True)
        .join(CampaignTarget, CampaignTarget.contact_id == Contact.id)
        .where(CampaignTarget.campaign_id == campaign_id)
    )
    res = await db.execute(stmt)
    out = []
    for contact, business in res.all():
        out.append({
            "contact_id": contact.id,
            "name": " ".join(p for p in (contact.first_name, contact.last_name) if p) or None,
            "email": contact.email,
            "business_name": business.name if business else None,
            "is_verified": bool(contact.is_verified),
        })
    return {"campaign_id": campaign_id, "targets": out}


@router.delete("/{campaign_id}/targets/{contact_id}")
async def remove_campaign_target(
    campaign_id: int, contact_id: int, db: AsyncSession = Depends(get_db)
):
    """Removes one recipient from a campaign."""
    stmt = select(CampaignTarget).where(
        CampaignTarget.campaign_id == campaign_id,
        CampaignTarget.contact_id == contact_id,
    )
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    await db.delete(row)
    await db.commit()
    return {"removed": True}


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    steps_stmt = select(CampaignStep).where(CampaignStep.campaign_id == campaign_id).order_by(CampaignStep.step_number.asc())
    steps_res = await db.execute(steps_stmt)
    steps = steps_res.scalars().all()

    sends_stmt = select(Send).where(Send.campaign_id == campaign_id).order_by(Send.created_at.desc()).limit(50)
    sends_res = await db.execute(sends_stmt)
    sends = sends_res.scalars().all()

    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "steps": [
            {
                "id": s.id,
                "step_number": s.step_number,
                "subject": s.subject,
                "body_text": s.body_text,
                "delay_days": s.delay_days
            }
            for s in steps
        ],
        "sends": [
            {
                "id": snd.id,
                "status": snd.status,
                "opened": snd.opened,
                "replied": snd.replied,
                "error_message": snd.error_message,
                "sent_at": snd.sent_at.isoformat() if snd.sent_at else None
            }
            for snd in sends
        ]
    }


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = CampaignStatus.ACTIVE.value
    await db.commit()

    background_tasks.add_task(execute_campaign_step, campaign_id)
    return {"status": "active", "message": f"Campaign '{campaign.name}' launched"}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = CampaignStatus.PAUSED.value
    await db.commit()
    return {"status": "paused", "message": f"Campaign '{campaign.name}' paused"}


@router.post("/preview")
async def preview_template(req: PreviewRequest):
    default_sample = {
        "business_name": "Balaji Properties",
        "first_name": "Rajesh",
        "last_name": "Sharma",
        "phone": "+91 98112 34567",
        "city": "Rohini, Delhi",
        "category": "Real Estate Agency",
        "website": "https://balajiproperties.example.in"
    }
    sample = {**default_sample, **(req.sample_data or {})}

    rendered_subject = interpolate_template(req.subject, sample)
    rendered_body = interpolate_template(req.body, sample)

    return {
        "sample_variables_used": sample,
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body
    }


from app.campaigns.spam_checker import check_cold_email_spam

class SpamCheckRequest(BaseModel):
    subject: str
    body: str

@router.post("/check-spam")
async def check_email_deliverability(req: SpamCheckRequest):
    """
    Evaluates cold outreach copy against spam filters, trigger words,
    subject line hygiene, and delivers actionable recommendations.
    """
    result = check_cold_email_spam(req.subject, req.body)
    return result


# --- India advisor (advisory only: nothing here blocks, gates or sends) ------

from app.campaigns.india_advisor import check_sender_auth, dlt_checklist, in_quiet_hours
from app.campaigns.india_copy import festival_context, hinglish_closers, culture_checklist
from app.campaigns.engagement import whatsapp_handoff, engagement_summary


class DltCheckRequest(BaseModel):
    numbers: List[str] = []


@router.get("/india/advisor")
async def india_advisor(domain: Optional[str] = None):
    """One-shot India readiness report for the dashboard banner.

    Sender auth (SPF/DKIM/DMARC) when a domain is given, TRAI quiet-hours
    state, and the current festival hook. Pure advice — the operator
    decides what to do; no send is ever gated here.
    """
    out: Dict[str, Any] = {
        "quiet_hours_now": in_quiet_hours(),
        "festival": festival_context(),
        "auth": check_sender_auth(domain) if domain else None,
    }
    return out


@router.post("/india/dlt-checklist")
async def india_dlt_checklist(req: DltCheckRequest):
    """TRAI/DLT posture report for a batch of numbers. Advisory only."""
    return dlt_checklist(req.numbers)


@router.get("/india/copy")
async def india_copy_kit():
    """Hinglish closers, festival hook, and the India copy do/don't checklist."""
    return {
        "festival": festival_context(),
        "hinglish_closers": hinglish_closers(),
        "culture_checklist": culture_checklist(),
    }


@router.get("/india/handoff/{campaign_id}")
async def india_warm_handoff(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """Contacts eligible for a *warm* WhatsApp handoff after email engagement.

    Surfaces (never sends) contacts who opened/clicked the email — the only
    WhatsApp posture that survives Meta's anti-spam policy: WhatsApp advances
    deals it knows, cold WhatsApp gets numbers reported.
    """
    stmt = select(Send).where(Send.campaign_id == campaign_id)
    res = await db.execute(stmt)
    sends = res.scalars().all()

    by_contact: Dict[int, List[Send]] = {}
    for s in sends:
        by_contact.setdefault(s.contact_id, []).append(s)

    candidates = []
    if by_contact:
        c_res = await db.execute(
            select(Contact).where(Contact.id.in_(list(by_contact.keys())))
        )
        for contact in c_res.scalars().all():
            c_sends = by_contact.get(contact.id, [])
            advice = whatsapp_handoff(
                c_sends, bool(contact.whatsapp_link) and not contact.unsubscribed
            )
            if advice["suggest"]:
                candidates.append({
                    "contact_id": contact.id,
                    "name": " ".join(
                        p for p in (contact.first_name, contact.last_name) if p
                    ) or None,
                    "whatsapp_link": contact.whatsapp_link,
                    "engagement": engagement_summary(c_sends),
                    "reason": advice["reason"],
                })
    return {"campaign_id": campaign_id, "candidates": candidates,
            "note": "Advisory: LeadForge never auto-sends WhatsApp; open the "
                    "link and write a personal message."}
