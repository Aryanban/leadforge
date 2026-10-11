"""Mailbox warmup, health, and rolling send budget.

Why this module exists: Gmail/Yahoo (Feb 2024+) throttle and bulk-folder
senders with no reputation history. A fresh mailbox that fires 50 cold
emails on day one gets flagged; the same mailbox ramped 10 -> 20 -> 40
over two weeks, with bounces kept under ~5%, builds a usable reputation.

Three mechanisms:

1. **Ramp schedule** (:func:`ramp_limit`): a mailbox younger than
   ``RAMP_DAYS`` gets a growing daily cap regardless of its configured
   ``daily_limit``. ``warming_up`` mailboxes are also preferred *last* in
   rotation so aged mailboxes absorb volume first.
2. **Health score** (:func:`mailbox_health`): computed from the last N sends
   (bounce rate dominates, failures count half). Below
   ``HEALTH_PAUSE_THRESHOLD`` the mailbox is gated out of rotation until a
   human reviews it - a sick mailbox poisons every campaign it touches.
3. **Rolling 24h budget** (:func:`rolling_24h_count`): ``sent_today`` is a
   calendar-day counter that never resets on its own (and drifts across
   timezones). The rolling count over actual ``Send.sent_at`` timestamps is
   the authoritative gate; ``sent_today`` is kept only as a fast pre-filter.

All functions are pure over simple inputs (age, counts) except the two
marked async, which query ``Send`` rows. That keeps the policy unit
testable without a database.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

#: Days from mailbox creation to full ``daily_limit``.
RAMP_DAYS = 14
#: Day-one cap for a brand-new mailbox. Doubling-ish curve to full limit.
RAMP_START = 10
#: Bounce rate (0-1) above which a mailbox is gated out of rotation.
HEALTH_PAUSE_THRESHOLD = 0.08
#: Sends looked at for the health score. Small enough to react quickly,
#: large enough that one stray bounce doesn't sideline a good mailbox.
HEALTH_WINDOW = 50


def mailbox_age_days(created_at: Optional[datetime], now: Optional[datetime] = None) -> int:
    """Age in whole days; unknown creation counts as fully warmed."""
    if created_at is None:
        return RAMP_DAYS
    now = now or datetime.now(timezone.utc)
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return max(0, (moment - created).days)


def ramp_limit(daily_limit: int, age_days: int) -> int:
    """Effective daily cap for a mailbox ``age_days`` old.

    Linear ramp from ``RAMP_START`` to ``daily_limit`` over ``RAMP_DAYS``;
    a fully aged mailbox gets its configured limit uncapped.
    """
    daily_limit = max(1, int(daily_limit or 50))
    if age_days >= RAMP_DAYS:
        return daily_limit
    span = max(1, daily_limit - RAMP_START)
    return max(1, RAMP_START + (span * age_days) // RAMP_DAYS)


def mailbox_health(bounced: int, failed: int, sent: int) -> float:
    """Reputation score in [0, 1]. 1.0 = clean; bounces hurt twice as much.

    A mailbox with no history scores 1.0 (innocent until proven guilty) so
    new mailboxes can enter the ramp.
    """
    total = (bounced or 0) + (failed or 0) + (sent or 0)
    if total <= 0:
        return 1.0
    penalty = (2.0 * (bounced or 0) + 0.5 * (failed or 0)) / total
    return round(max(0.0, 1.0 - penalty), 3)


def is_mailbox_usable(health: float, age_days: int) -> tuple:
    """``(usable, reason)`` gate for rotation.

    A mailbox still in its ramp is usable but deprioritised (reason
    ``\"warming_up\"``); a mailbox under the health threshold is gated out
    (``\"health_pause\"``) until reviewed.
    """
    if health < HEALTH_PAUSE_THRESHOLD:
        return False, "health_pause"
    if age_days < RAMP_DAYS:
        return True, "warming_up"
    return True, "ready"


async def rolling_24h_count(db, mailbox_id: int, now: Optional[datetime] = None) -> int:
    """Authoritative sends-in-the-last-24h for one mailbox.

    Counts ``Send`` rows with ``sent_at`` inside the window instead of
    trusting ``Mailbox.sent_today``, which is a calendar-day counter that
    nothing resets and that drifts across timezones.
    """
    from sqlalchemy import select, func as sa_func
    from app.models.send import Send

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    stmt = (
        select(sa_func.count())
        .select_from(Send)
        .where(Send.mailbox_id == mailbox_id, Send.sent_at.isnot(None),
               Send.sent_at >= cutoff)
    )
    res = await db.execute(stmt)
    return int(res.scalar() or 0)


async def recent_outcomes(db, mailbox_id: int, limit: int = HEALTH_WINDOW) -> tuple:
    """``(bounced, failed, sent)`` over a mailbox's last ``limit`` sends."""
    from sqlalchemy import select
    from app.models.send import Send

    stmt = (
        select(Send.status)
        .where(Send.mailbox_id == mailbox_id)
        .order_by(Send.id.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    bounced = failed = sent = 0
    for (status,) in res.all():
        if status == "bounced":
            bounced += 1
        elif status == "failed":
            failed += 1
        elif status == "sent":
            sent += 1
    return bounced, failed, sent
