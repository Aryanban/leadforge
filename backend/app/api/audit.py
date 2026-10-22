"""The audit feed.

"Which decisions did the product make, and why?" - the question a
self-hosted tool has to be able to answer without reading the source.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_event import EVENTS, AuditEvent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
@router.get("/")
async def list_audit_events(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(
        None, description="Filter to one kind of event, e.g. email_sent."
    ),
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """The recent activity feed, newest first."""
    stmt = select(AuditEvent)
    count_stmt = select(func.count(AuditEvent.id))

    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
        count_stmt = count_stmt.where(AuditEvent.event_type == event_type)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
        count_stmt = count_stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
        count_stmt = count_stmt.where(AuditEvent.entity_id == entity_id)

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )).scalars().all()

    return {
        "total": total,
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_label": EVENTS.get(e.event_type, e.event_type),
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "actor": e.actor,
                "summary": e.summary,
                "detail": e.detail,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ],
    }


@router.get("/types")
async def audit_event_types(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """The event vocabulary, with a count for each.

    A filter list built from the vocabulary is discoverable; one built
    from a hard-coded array in the UI is not.
    """
    rows = (await db.execute(
        select(AuditEvent.event_type, func.count(AuditEvent.id))
        .group_by(AuditEvent.event_type)
        .order_by(func.count(AuditEvent.id).desc())
    )).all()
    counts = {event_type: count for event_type, count in rows}

    out: List[Dict[str, Any]] = []
    for event_type, label in EVENTS.items():
        out.append({
            "event_type": event_type,
            "label": label,
            "count": counts.get(event_type, 0),
        })
    # Anything recorded by a newer version of the code than this file
    # knows about still has to appear, or the filter would hide it.
    for event_type, count in counts.items():
        if event_type not in EVENTS:
            out.append({
                "event_type": event_type,
                "label": event_type.replace("_", " ").capitalize(),
                "count": count,
            })
    return {"types": out}
