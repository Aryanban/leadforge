"""Suppression enforcement.

Every outbound path must pass through :func:`is_suppressed` before sending.
There are four gates in a healthy pipeline:

  1. import      - drop blocklisted rows as they land
  2. enrich      - do not pay to verify an address we will never mail
  3. queue       - the authoritative check, immediately before the SMTP call
  4. reply       - an inbound "stop" must suppress before the next batch

This module owns the SQL so that every gate agrees on the rules.
"""

import logging
from typing import Dict, Iterable, Optional, Set

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suppression import Suppression, PERMANENT_REASONS

logger = logging.getLogger(__name__)


def email_domain(email: Optional[str]) -> Optional[str]:
    """``Name@Example.COM`` -> ``example.com``."""
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].strip().lower()


def _domain_key(email: str) -> str:
    """Whole-domain suppression key: ``example.com`` -> ``@example.com``."""
    return f"@{email_domain(email)}"


async def is_suppressed(
    db: AsyncSession,
    email: Optional[str],
    *,
    include_expired: bool = False,
) -> Optional[str]:
    """Returns the suppression reason if this address must not be mailed.

    Checks both the exact address and its whole-domain entry, and ignores
    expired soft-bounce entries unless ``include_expired`` is set.
    """
    if not email:
        return None

    addr = email.strip().lower()
    keys = [addr]
    domain_key = _domain_key(addr)
    if domain_key != "@":
        keys.append(domain_key)

    stmt = select(Suppression).where(Suppression.identifier.in_(keys))

    # Expiry is evaluated in Python via `row.is_active()` because SQLite's
    # timezone-aware comparison differs from Postgres - keeping one code path
    # means both backends enforce identical rules.

    for row in (await db.execute(stmt)).scalars().all():
        if row.is_active():
            logger.debug("suppressed %s (%s)", addr, row.reason)
            return row.reason

    return None


async def suppressed_reasons(
    db: AsyncSession,
    emails: Iterable[Optional[str]],
) -> Dict[str, str]:
    """Batch form of :func:`is_suppressed`. Maps address -> suppression reason.

    The campaign sender used to call ``is_suppressed`` once per candidate
    contact - one round-trip each, so a 500-target campaign spent 500
    queries deciding who *not* to email. One query answers the whole set.
    """
    cleaned = {e.strip().lower() for e in emails if e and "@" in e}
    if not cleaned:
        return {}

    keys: Set[str] = set(cleaned)
    for addr in cleaned:
        keys.add(_domain_key(addr))
    keys.discard("@")

    rows = (
        await db.execute(select(Suppression).where(Suppression.identifier.in_(keys)))
    ).scalars().all()

    live = [r for r in rows if r.is_active()]
    out: Dict[str, str] = {}
    for row in live:
        if row.is_domain:
            suffix = row.identifier
            for addr in cleaned:
                if addr.endswith(suffix):
                    out.setdefault(addr, row.reason)
        else:
            out.setdefault(row.identifier, row.reason)
    return out


async def filter_suppressed(
    db: AsyncSession,
    emails: Iterable[Optional[str]],
) -> Set[str]:
    """Batch form of :func:`is_suppressed`. Returns the blocked addresses."""
    reasons = await suppressed_reasons(db, emails)
    return set(reasons.keys())


async def add_suppression(
    db: AsyncSession,
    email: Optional[str],
    reason: str,
    detail: Optional[str] = None,
    *,
    domain_wide: bool = False,
) -> bool:
    """Adds a suppression entry. Idempotent. Returns True if newly added."""
    if not email or "@" not in email:
        return False

    identifier = _domain_key(email) if domain_wide else email.strip().lower()
    existing = (
        await db.execute(select(Suppression).where(Suppression.identifier == identifier))
    ).scalar_one_or_none()

    if existing is not None:
        # Never downgrade a permanent reason to a transient one.
        if existing.reason in PERMANENT_REASONS and reason not in PERMANENT_REASONS:
            return False
        existing.reason = reason
        existing.detail = detail
        # A row created as a soft bounce carries an expiry. If it is later
        # upgraded to a permanent reason the expiry has to go, otherwise the
        # hard-bounce suppression silently ages out and the dead address
        # becomes mailable again.
        if reason in PERMANENT_REASONS:
            existing.expires_at = None
        await db.flush()
        return False

    db.add(Suppression.make(identifier, reason, detail))
    await db.flush()
    return True


async def purge_expired(db: AsyncSession) -> int:
    """Deletes soft-bounce rows whose retry window has passed."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(Suppression).where(
            Suppression.expires_at.isnot(None),
            Suppression.expires_at < now,
        )
    )
    await db.flush()
    return result.rowcount or 0
