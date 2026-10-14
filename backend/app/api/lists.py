"""Saved lead views (Apollo-style dynamic lists).

A saved view is a name plus the filter object the Lead Database page
speaks (``search`` / ``industry`` / ``has_email``). One row here = one
clickable saved segment; the underlying query always runs live.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.database import get_db
from app.models.saved_list import SavedList

router = APIRouter()


class SavedListCreate(BaseModel):
    name: str
    filters: Optional[Dict[str, Any]] = None


@router.get("")
async def list_saved(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(SavedList).order_by(SavedList.id.desc())
    )).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "filters": r.filters or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("")
async def save_view(req: SavedListCreate, db: AsyncSession = Depends(get_db)):
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    row = SavedList(name=name, filters=req.filters or {})
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "name": row.name, "filters": row.filters or {}}


@router.delete("/{list_id}")
async def delete_view(list_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(SavedList, list_id)
    if not row:
        raise HTTPException(status_code=404, detail="Saved view not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": True, "id": list_id}
