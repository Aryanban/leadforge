from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.discovery.pipeline import run_discovery
from app.models.icp_profile import ICPProfile
from app.models.scrape_job import ScrapeJob
from app.qualifier.nl_icp import parse_icp_text
from app.qualifier.ranker import rank_existing

router = APIRouter()


class ICPProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field(..., min_length=1)
    area: Optional[str] = None
    keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    signal_weights: Optional[Dict[str, float]] = None
    min_score: int = Field(45, ge=0, le=100)
    preset: str = "outreach_quality"
    preferred_sources: Optional[List[str]] = None


class ICPProfileCreate(ICPProfileBase):
    pass


class ICPProfileUpdate(BaseModel):
    name: Optional[str] = None
    niche: Optional[str] = None
    area: Optional[str] = None
    keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    signal_weights: Optional[Dict[str, float]] = None
    min_score: Optional[int] = Field(None, ge=0, le=100)
    preset: Optional[str] = None
    preferred_sources: Optional[List[str]] = None


class ICPProfileOut(ICPProfileBase):
    id: int
    source_stats: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ParseRequest(BaseModel):
    text: str = Field(..., min_length=3, example="Dentists in South Delhi with verified emails")


class DiscoverRequest(BaseModel):
    niche: str = Field(..., min_length=2, example="Dentists")
    area: Optional[str] = Field(None, example="South Delhi")
    icp_profile_id: int
    max_results: int = Field(20, ge=1, le=100)
    sources: Optional[List[str]] = None


def _profile_to_dict(profile: ICPProfile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "niche": profile.niche,
        "area": profile.area,
        "keywords": profile.keywords or [],
        "exclude_keywords": profile.exclude_keywords or [],
        "signal_weights": profile.signal_weights or {},
        "min_score": profile.min_score,
        "preset": profile.preset,
        "preferred_sources": profile.preferred_sources or [],
        "source_stats": profile.source_stats or {},
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.post("", response_model=ICPProfileOut)
@router.post("/", response_model=ICPProfileOut, include_in_schema=False)
async def create_icp_profile(payload: ICPProfileCreate, db: AsyncSession = Depends(get_db)):
    if payload.preset not in ("outreach_quality", "agency_opportunity"):
        raise HTTPException(status_code=422, detail="preset must be outreach_quality or agency_opportunity")

    profile = ICPProfile(
        name=payload.name,
        niche=payload.niche,
        area=payload.area,
        keywords=payload.keywords,
        exclude_keywords=payload.exclude_keywords,
        signal_weights=payload.signal_weights,
        min_score=payload.min_score,
        preset=payload.preset,
        preferred_sources=payload.preferred_sources,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_dict(profile)


@router.get("")
@router.get("/")
async def list_icp_profiles(db: AsyncSession = Depends(get_db)):
    stmt = select(ICPProfile).order_by(ICPProfile.created_at.desc())
    res = await db.execute(stmt)
    return [_profile_to_dict(p) for p in res.scalars().all()]


@router.get("/{profile_id}")
async def get_icp_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ICPProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")
    return _profile_to_dict(profile)


@router.put("/{profile_id}")
async def update_icp_profile(profile_id: int, payload: ICPProfileUpdate, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ICPProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")

    data = payload.model_dump(exclude_unset=True)
    if "preset" in data and data["preset"] not in ("outreach_quality", "agency_opportunity"):
        raise HTTPException(status_code=422, detail="preset must be outreach_quality or agency_opportunity")

    for key, value in data.items():
        setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)
    return _profile_to_dict(profile)


@router.delete("/{profile_id}")
async def delete_icp_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ICPProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")
    await db.delete(profile)
    await db.commit()
    return {"deleted": profile_id}


@router.post("/parse")
async def parse_icp(payload: ParseRequest):
    """Turn natural-language intent into a draft ICP profile for the wizard."""
    return parse_icp_text(payload.text)


@router.post("/{profile_id}/rank")
async def rank_leads_for_profile(
    profile_id: int,
    limit: int = 50,
    scope_icp: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Rank the leads already in the database against this ICP profile."""
    profile = await db.get(ICPProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")

    ranked = await rank_existing(db, profile, limit=limit, scope_icp=scope_icp)
    return {
        "icp_profile_id": profile.id,
        "min_score": profile.min_score,
        "total": len(ranked),
        "ranked_leads": ranked,
    }


@router.post("/discover")
async def start_discovery(
    payload: DiscoverRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Find the best leads for a niche+area against an ICP profile."""
    profile = await db.get(ICPProfile, payload.icp_profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="ICP profile not found")

    query = f"{payload.niche} in {payload.area}".strip() if payload.area else payload.niche.strip()
    job = ScrapeJob(
        query=query,
        status="pending",
        total_found=0,
        leads_saved=0,
        icp_profile_id=profile.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(
        run_discovery,
        job_id=job.id,
        niche=payload.niche,
        area=payload.area,
        icp_profile_id=profile.id,
        max_results=payload.max_results,
        sources=payload.sources,
    )

    return {
        "job_id": job.id,
        "icp_profile_id": profile.id,
        "query": job.query,
        "status": "started",
        "message": f"Discovery started for '{query}'",
    }


@router.get("/discover/{job_id}")
async def get_discovery_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ScrapeJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")
    return {
        "id": job.id,
        "query": job.query,
        "status": job.status,
        "total_found": job.total_found,
        "leads_saved": job.leads_saved,
        "error": job.error,
        "icp_profile_id": job.icp_profile_id,
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
