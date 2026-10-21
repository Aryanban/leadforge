"""Global suppression list.

A per-contact ``unsubscribed`` boolean is not enough: it is scoped to one row,
so the same address can be re-imported by a later scrape and mailed again.
Suppression must be workspace-wide and reason-coded, and it must cover the
whole domain (a "do not contact this company" request is not a per-person
request).

Reasons
-------
``unsubscribed``  the recipient clicked one-click unsubscribe (RFC 8058)
``replied_stop``  they replied "stop"/"remove me"
``hard_bounce``   permanent 5xx - the mailbox does not exist
``soft_bounce``   transient, repeated past the retry budget
``complaint``     marked spam
``manual``        an operator blocked them
``import``        supplied as a pre-existing blocklist on CSV import

Lifetime
--------
Unsubscribed / complaint / manual entries are permanent. ``hard_bounce``
entries are permanent too (the address will never exist). ``soft_bounce``
expires after ``expires_at`` so a transient gateway failure does not burn a
lead forever.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base

#: Reasons that never expire.
PERMANENT_REASONS = frozenset({
    "unsubscribed", "replied_stop", "hard_bounce", "complaint", "manual", "import",
})

#: How long a soft bounce keeps a lead out of rotation before we retry.
SOFT_BOUNCE_RETENTION_DAYS = 30


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    A naive ``utcnow()`` written into a ``DateTime(timezone=True)`` column is
    interpreted as *server-local* time by Postgres, which shifts every
    expiry by the host's UTC offset (India is +5:30).
    """
    return datetime.now(timezone.utc)


class Suppression(Base):
    __tablename__ = "suppressions"

    id = Column(Integer, primary_key=True, index=True)

    #: Lowercased email address, or ``@domain.tld`` for a whole-domain block.
    identifier = Column(String, index=True, nullable=False)

    reason = Column(String, index=True, nullable=False)

    #: Free-text detail - SMTP code, campaign id, operator note.
    detail = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    #: NULL means permanent. Soft bounces set a future timestamp.
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    @property
    def is_domain(self) -> bool:
        return self.identifier.startswith("@")

    def is_active(self, now: Optional[datetime] = None) -> bool:
        """False only for an expired soft-bounce entry."""
        if self.expires_at is None:
            return True
        expiry = self.expires_at
        reference = now or _utcnow()
        # SQLite returns naive datetimes, Postgres returns aware ones.
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return expiry > reference

    @classmethod
    def make(
        cls,
        identifier: str,
        reason: str,
        detail: Optional[str] = None,
        retention_days: Optional[int] = None,
    ) -> "Suppression":
        """Builds a row, setting ``expires_at`` for reasons that should age out."""
        expires_at = None
        if reason not in PERMANENT_REASONS and retention_days is not None:
            expires_at = _utcnow() + timedelta(days=retention_days)
        elif reason == "soft_bounce":
            expires_at = _utcnow() + timedelta(days=SOFT_BOUNCE_RETENTION_DAYS)

        return cls(
            identifier=identifier.strip().lower(),
            reason=reason,
            detail=detail,
            expires_at=expires_at,
        )
