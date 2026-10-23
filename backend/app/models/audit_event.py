"""The audit log.

A cold-email tool makes decisions that are invisible from the outside: a
lead was skipped, an address was suppressed, a send was deferred, a
subject variant won. Without a record of those decisions the only way to
answer "why did this lead get no email?" is to read the source.

Every event carries the *why* in a sentence, because a log of codes is
only useful to the person who wrote the codes.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.database import Base

logger = logging.getLogger(__name__)


class AuditEvent(Base):
    """One thing the product did, and why."""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    #: What happened: ``email_sent``, ``email_bounced``, ``lead_suppressed``,
    #: ``send_deferred``, ``campaign_launched``, ``ab_winner_declared``,
    #: ``job_recovered``, ``icp_filtered``...
    event_type = Column(String, index=True, nullable=False)
    #: What it happened to: ``lead``, ``contact``, ``campaign``, ``mailbox``,
    #: ``job``, ``icp``.
    entity_type = Column(String, index=True, nullable=True)
    entity_id = Column(Integer, index=True, nullable=True)
    #: Who did it. ``system`` for anything automatic; the operator's email
    #: for a manual action.
    actor = Column(String, default="system", nullable=True, index=True)
    #: A sentence a human can read. This is the field that makes the log
    #: worth having.
    summary = Column(String, nullable=True)
    #: The structured detail - the addresses, the counts, the reasons.
    detail = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


#: The event types, so the vocabulary is discoverable rather than a set of
#: strings scattered through the codebase.
EVENTS = {
    "lead_discovered": "A business was found",
    "lead_enriched": "A business was enriched",
    "contact_identified": "A person was identified at a business",
    "email_sent": "An email was sent",
    "email_bounced": "An email bounced",
    "email_opened": "An email was opened",
    "email_replied": "A reply was received",
    "lead_suppressed": "An address was suppressed",
    "send_deferred": "A send was deferred to a better hour",
    "campaign_launched": "A sequence was launched",
    "campaign_paused": "A sequence was paused",
    "ab_winner_declared": "A subject variant won the A/B test",
    "job_recovered": "A job was recovered after a restart",
    "icp_filtered": "A lead was filtered out by the ICP",
    "source_failed": "A data source could not be read",
}


async def record(
    db: Any,
    event_type: str,
    summary: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    actor: str = "system",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Records one event.

    Never raises: an audit failure must not break the action being audited.
    The event is written in the caller's transaction, so it commits with
    the work it describes.
    """
    try:
        db.add(
            AuditEvent(
                event_type=event_type,
                summary=summary,
                entity_type=entity_type,
                entity_id=entity_id,
                actor=actor,
                detail=detail or None,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("audit event not recorded (%s): %s", event_type, exc)
