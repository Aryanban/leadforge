from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models.business import Business
from app.enricher.email_finder import enrich_business_by_id, enrich_all_pending_businesses

router = APIRouter()

@router.post("/enrich-lead/{business_id}")
async def enrich_lead(business_id: int, db: AsyncSession = Depends(get_db)):
    business = await db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    if not business.website:
        raise HTTPException(status_code=400, detail="Business has no website to crawl")

    result = await enrich_business_by_id(business_id)
    return result

@router.post("/enrich-all")
async def trigger_bulk_enrichment(
    background_tasks: BackgroundTasks,
    limit: int = 25,
    db: AsyncSession = Depends(get_db)
):
    background_tasks.add_task(enrich_all_pending_businesses, limit)
    return {
        "status": "queued",
        "message": f"Bulk enrichment initiated for up to {limit} businesses with websites"
    }
