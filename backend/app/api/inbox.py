"""Inbox: inbound replies detected by the IMAP reply poller.

Reads only — detection happens in ``app/campaigns/reply_poller.py`` (header
attribution via stored Message-IDs, opt-out suppression at capture time).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.database import get_db
from app.models.send import Send
from app.models.contact import Contact
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.campaign_step import CampaignStep

router = APIRouter()

CATEGORIES = ("interested", "not_interested", "opt_out", "out_of_office", "other")


class CategorySet(BaseModel):
    category: str


@router.get("")
async def list_replies(
    category: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    stmt = (
        select(Send, Contact, Business, Campaign, CampaignStep)
        .outerjoin(Contact, Contact.id == Send.contact_id)
        .outerjoin(Business, Business.id == Contact.business_id)
        .outerjoin(Campaign, Campaign.id == Send.campaign_id)
        .outerjoin(CampaignStep, CampaignStep.id == Send.step_id)
        .where(Send.replied == True)
        .order_by(Send.replied_at.desc().nullslast(), Send.id.desc())
        .limit(min(limit, 500))
    )
    if category:
        stmt = stmt.where(Send.reply_category == category)
    res = await db.execute(stmt)

    counts = {cat: 0 for cat in CATEGORIES}
    # One grouped query instead of one COUNT per category.
    count_rows = (await db.execute(
        select(Send.reply_category, func.count(Send.id))
        .where(Send.replied == True)
        .group_by(Send.reply_category)
    )).all()
    for category, count in count_rows:
        if category:
            counts[category] = count

    items = []
    for send, contact, business, campaign, step in res.all():
        name = None
        if contact is not None:
            name = " ".join(
                p for p in (contact.first_name, contact.last_name) if p
            ) or None
        items.append({
            "send_id": send.id,
            "category": send.reply_category or "other",
            "replied_at": send.replied_at.isoformat() if send.replied_at else None,
            "reply_body": send.reply_body,
            "contact_name": name,
            "contact_email": contact.email if contact else None,
            "business_name": business.name if business else None,
            "campaign_id": send.campaign_id,
            "campaign_name": campaign.name if campaign else None,
            "step_subject": step.subject if step else None,
            "mailbox_id": send.mailbox_id,
        })
    return {"items": items, "counts": counts}


@router.post("/{send_id}/category")
async def recategorize(send_id: int, req: CategorySet,
                       db: AsyncSession = Depends(get_db)):
    """Human override of a reply category (agents triage, humans confirm)."""
    if req.category not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {list(CATEGORIES)}")
    send = await db.get(Send, send_id)
    if not send:
        raise HTTPException(status_code=404, detail="Send not found")
    send.reply_category = req.category
    await db.commit()
    return {"send_id": send_id, "category": req.category}
