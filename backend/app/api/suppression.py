"""Global suppression list (workspace-wide do-not-contact).

The MCP server already exposes add/list; these are the dashboard's REST
equivalents. Reasons: unsubscribed, replied_stop, hard_bounce, soft_bounce,
complaint, manual, import. Permanent reasons never expire; soft bounces age
out (see ``Suppression.make``).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.database import get_db
from app.models.suppression import Suppression
from app.campaigns.suppression import add_suppression

router = APIRouter()


class SuppressionAdd(BaseModel):
    identifier: str
    reason: str = "manual"
    detail: Optional[str] = None
    domain_wide: bool = False


@router.get("")
async def list_suppressions(
    active_only: bool = False,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    rows = (await db.execute(
        select(Suppression).order_by(Suppression.id.desc()).limit(min(limit, 1000))
    )).scalars().all()
    items = [
        {
            "id": r.id,
            "identifier": r.identifier,
            "reason": r.reason,
            "detail": r.detail,
            "is_domain": r.is_domain,
            "active": r.is_active(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    if active_only:
        items = [i for i in items if i["active"]]
    return {"items": items, "total": len(items)}


@router.post("")
async def add_suppression_entry(req: SuppressionAdd,
                                db: AsyncSession = Depends(get_db)):
    identifier = (req.identifier or "").strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="identifier is required")
    domain_wide = req.domain_wide or identifier.startswith("@")
    if domain_wide and "@" not in identifier:
        raise HTTPException(
            status_code=422,
            detail="For a whole-domain block, pass the domain as '@domain.com'",
        )
    newly = await add_suppression(db, identifier, req.reason or "manual",
                                   detail=req.detail, domain_wide=domain_wide)
    await db.commit()
    return {"added": newly, "identifier": identifier, "reason": req.reason}
