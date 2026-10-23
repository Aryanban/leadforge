"""The India send window.

An email that lands at 03:00 IST is marked as spam by a human, not a
filter - the recipient is asleep. Every serious cold-email tool schedules
to the recipient's local business hours; this one did not, because the
product's whole market is IST.

The send is *deferred*, never dropped: the contact is not marked as sent,
so the scheduler picks it up on its next tick, which is inside the
window.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.campaigns.india_advisor import (
    EMAIL_SEND_END_HOUR,
    EMAIL_SEND_START_HOUR,
    in_email_send_window,
    next_send_window_opens,
)
from app.campaigns.sender import _is_india_lead


def _ist(hour: int, minute: int = 0) -> datetime:
    """A UTC datetime that is the given wall-clock hour in IST."""
    from zoneinfo import ZoneInfo

    local = datetime(2026, 10, 22, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))
    return local.astimezone(timezone.utc)


def test_the_window_is_the_business_day():
    assert in_email_send_window(_ist(9, 30)) is True
    assert in_email_send_window(_ist(13, 0)) is True
    assert in_email_send_window(_ist(19, 59)) is True


def test_the_small_hours_are_outside_the_window():
    assert in_email_send_window(_ist(3, 0)) is False
    assert in_email_send_window(_ist(8, 59)) is False
    assert in_email_send_window(_ist(20, 0)) is False
    assert in_email_send_window(_ist(23, 30)) is False


def test_the_next_window_time_is_human_readable():
    assert next_send_window_opens(_ist(3, 0)) == f"{EMAIL_SEND_START_HOUR:02d}:00 IST"
    assert next_send_window_opens(_ist(22, 0)) == f"{EMAIL_SEND_START_HOUR:02d}:00 IST tomorrow"
    # Inside the window there is no next window to wait for.
    assert next_send_window_opens(_ist(13, 0)) is None


class _Obj:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_a_lead_is_recognised_as_indian():
    assert _is_india_lead(_Obj(phone="+91 98225 22560")) is True
    assert _is_india_lead(_Obj(phone="098225 22560")) is True
    assert _is_india_lead(_Obj(phone=None, state="Maharashtra")) is True
    assert _is_india_lead(_Obj(phone=None, state="Gujarat")) is True


def test_a_non_indian_lead_is_not():
    assert _is_india_lead(_Obj(phone="+1 512 555 0100", state="Texas")) is False
    assert _is_india_lead(_Obj(phone=None, state=None)) is False
    assert _is_india_lead(_Obj(phone=None, state="California")) is False


@pytest.mark.asyncio
async def test_an_indian_send_outside_the_window_is_deferred(monkeypatch):
    """The send is deferred, not dropped and not failed."""
    from app.database import async_session_maker
    from app.models.business import Business
    from app.models.campaign import Campaign, CampaignStatus
    from app.models.campaign_step import CampaignStep, CampaignTarget
    from app.models.contact import Contact
    from app.models.mailbox import Mailbox
    from app.campaigns import sender as sender_mod
    from app.campaigns.sender import execute_campaign_step

    # Pretend it is 03:00 IST.
    monkeypatch.setattr(
        "app.campaigns.india_advisor.in_email_send_window", lambda *a, **k: False
    )
    monkeypatch.setattr(
        "app.campaigns.india_advisor.next_send_window_opens",
        lambda *a, **k: "09:00 IST",
    )

    sent = []

    async def _fake_send(*args, **kwargs):
        sent.append(kwargs)
        return True, ""

    monkeypatch.setattr(sender_mod, "send_single_email_async", _fake_send)

    async with async_session_maker() as db:
        biz = Business(
            name="Pune Realty", industry="Real estate",
            phone="+91 98225 22560", city="Pune", state="Maharashtra",
        )
        db.add(biz)
        await db.flush()
        contact = Contact(
            business_id=biz.id, email="owner@example.in",
            phone="+91 98225 22560", verification_status="valid",
            is_verified=True, preferred_channel="whatsapp",
        )
        db.add(contact)
        await db.flush()
        campaign = Campaign(name="Window Test", status=CampaignStatus.ACTIVE.value)
        db.add(campaign)
        await db.flush()
        step = CampaignStep(
            campaign_id=campaign.id, step_number=1, subject="Hello",
            body_text="Hi {{first_name}}", delay_days=0,
        )
        db.add(step)
        await db.flush()
        db.add(CampaignTarget(campaign_id=campaign.id, contact_id=contact.id))
        db.add(Mailbox(
            email="sender@example.in", password="x", smtp_host="smtp.example.in",
            smtp_port=587, daily_limit=10, sent_today=0,
        ))
        await db.commit()
        campaign_id = campaign.id
        contact_id = contact.id

    result = await execute_campaign_step(campaign_id, max_sends=5)

    assert result["sent_count"] == 0
    assert result.get("deferred_count") == 1
    assert not sent, "nothing should have been sent"
    assert "deferred" in (result.get("message") or "").lower()

    # The contact is NOT marked as sent, so the scheduler retries it.
    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.models.send import Send

        rows = (await db.execute(
            select(Send).where(Send.contact_id == contact_id)
        )).scalars().all()
        assert not rows, "a deferred send must not leave a sent record"


@pytest.mark.asyncio
async def test_a_non_indian_send_is_not_deferred_by_the_india_window(monkeypatch):
    """A campaign with an American lead must not be held for IST."""
    from app.database import async_session_maker
    from app.models.business import Business
    from app.models.campaign import Campaign, CampaignStatus
    from app.models.campaign_step import CampaignStep, CampaignTarget
    from app.models.contact import Contact
    from app.models.mailbox import Mailbox
    from app.campaigns import sender as sender_mod
    from app.campaigns.sender import execute_campaign_step

    monkeypatch.setattr(
        "app.campaigns.india_advisor.in_email_send_window", lambda *a, **k: False
    )

    sent = []

    async def _fake_send(*args, **kwargs):
        sent.append(kwargs)
        return True, ""

    monkeypatch.setattr(sender_mod, "send_single_email_async", _fake_send)

    async with async_session_maker() as db:
        biz = Business(
            name="Austin Realty", industry="Real estate",
            phone="+1 512 555 0100", state="Texas",
        )
        db.add(biz)
        await db.flush()
        contact = Contact(
            business_id=biz.id, email="owner@example.com",
            phone="+1 512 555 0100", verification_status="valid", is_verified=True,
        )
        db.add(contact)
        await db.flush()
        campaign = Campaign(name="Window Test", status=CampaignStatus.ACTIVE.value)
        db.add(campaign)
        await db.flush()
        step = CampaignStep(
            campaign_id=campaign.id, step_number=1, subject="Hello",
            body_text="Hi {{first_name}}", delay_days=0,
        )
        db.add(step)
        await db.flush()
        db.add(CampaignTarget(campaign_id=campaign.id, contact_id=contact.id))
        db.add(Mailbox(
            email="sender@example.com", password="x", smtp_host="smtp.example.com",
            smtp_port=587, daily_limit=10, sent_today=0,
        ))
        await db.commit()
        campaign_id = campaign.id

    result = await execute_campaign_step(campaign_id, max_sends=5)

    assert result["sent_count"] == 1
    assert not result.get("deferred_count")
    assert sent
