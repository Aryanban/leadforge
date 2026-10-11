from datetime import datetime, timedelta, timezone

from app.campaigns.warmup import (
    mailbox_age_days, ramp_limit, mailbox_health, is_mailbox_usable,
    RAMP_DAYS, RAMP_START, HEALTH_PAUSE_THRESHOLD,
)


def test_ramp_starts_low_and_reaches_limit():
    assert ramp_limit(50, 0) == RAMP_START
    mid = ramp_limit(50, RAMP_DAYS // 2)
    assert RAMP_START < mid < 50
    assert ramp_limit(50, RAMP_DAYS) == 50
    assert ramp_limit(50, RAMP_DAYS + 30) == 50


def test_ramp_respects_small_configured_limit():
    assert ramp_limit(20, 0) == RAMP_START or ramp_limit(20, 0) <= 20
    assert ramp_limit(20, RAMP_DAYS) == 20


def test_health_clean_mailbox_scores_one():
    assert mailbox_health(0, 0, 40) == 1.0
    assert mailbox_health(0, 0, 0) == 1.0  # no history: innocent until proven guilty


def test_health_bounces_hurt_most():
    h_bounce = mailbox_health(4, 0, 46)
    h_fail = mailbox_health(0, 4, 46)
    assert h_bounce < h_fail < 1.0


def test_health_sick_mailbox_near_zero():
    assert mailbox_health(10, 0, 10) < HEALTH_PAUSE_THRESHOLD


def test_usable_gate():
    usable, reason = is_mailbox_usable(1.0, RAMP_DAYS + 1)
    assert (usable, reason) == (True, "ready")
    usable, reason = is_mailbox_usable(1.0, 2)
    assert (usable, reason) == (True, "warming_up")
    usable, reason = is_mailbox_usable(0.01, RAMP_DAYS + 5)
    assert (usable, reason) == (False, "health_pause")


def test_age_unknown_creation_counts_as_warmed():
    assert mailbox_age_days(None) == RAMP_DAYS


def test_age_whole_days():
    now = datetime.now(timezone.utc)
    assert mailbox_age_days(now - timedelta(days=3, hours=12), now) == 3
    assert mailbox_age_days(now + timedelta(days=1), now) == 0
