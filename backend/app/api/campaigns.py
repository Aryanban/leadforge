from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep
from app.models.send import Send
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

class PreviewRequest(BaseModel):
    subject: str
    body: str
    sample_data: Optional[Dict[str, str]] = None

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

        result.append({
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "total_targets": total_sends,
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

    await db.commit()
    return {"id": campaign.id, "name": campaign.name, "status": campaign.status}


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
