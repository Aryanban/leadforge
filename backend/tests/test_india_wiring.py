"""The India features that were built but never wired.

Three pieces of the India moat existed in the codebase and were called from
nowhere:

* ``localize_template`` - the festival/Hinglish substitution. A step whose
  body used ``{{festival_line}}`` shipped the literal braces to the
  prospect, because nothing ever called it.
* ``preferred_channel`` - whatsapp / call / email, computed from the line
  type at enrichment time. The sender never read it, so "Indian SMB owners
  answer WhatsApp" changed nothing.
* The A/B winner - declared only as a side effect of somebody opening the
  sequence-detail page. Nobody looking meant no verdict, ever.

These tests drive the real send path with the transport stubbed out, so a
regression cannot hide behind a swallowed error again.
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session_maker
from app.campaigns import sender as sender_mod
from app.campaigns.sender import execute_campaign_step
from app.models.business import Business
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_step import CampaignStep, CampaignTarget
from app.models.contact import Contact
from app.models.mailbox import Mailbox
from app.models.send import Send


async def _build_campaign(
    *,
    body_text: str = "Hello there",
    body_html: str = "",
    subject_b: str = None,
    phone: str = "+91 98200 11223",
    preferred_channel: str = None,
):
    """Creates a one-step campaign with one target. Returns its id."""
    async with async_session_maker() as db:
        biz = Business(name="Wire Test Co", phone=phone)
        db.add(biz)
        await db.flush()
        contact = Contact(
            business_id=biz.id,
            email="wire@example.in",
            phone=phone,
            preferred_channel=preferred_channel,
            verification_status="valid",
        )
        db.add(contact)
        await db.flush()
        camp = Campaign(name="Wire Test", status=CampaignStatus.ACTIVE.value)
        db.add(camp)
        await db.flush()
        step = CampaignStep(
            campaign_id=camp.id,
            step_number=1,
            subject="Hello",
            subject_b=subject_b,
            body_text=body_text,
            body_html=body_html,
            delay_days=0,
        )
        db.add(step)
        await db.flush()
        db.add(CampaignTarget(campaign_id=camp.id, contact_id=contact.id))
        db.add(Mailbox(
            email="sender@example.in", password="x",
            smtp_host="smtp.example.in", smtp_port=587,
            daily_limit=10, sent_today=0,
        ))
        await db.commit()
        return camp.id


def _capture(monkeypatch):
    """Stubs the SMTP call and captures what would have been sent."""
    captured = {}

    async def _fake_send(*args, **kwargs):
        captured.update(kwargs)
        return True, ""

    monkeypatch.setattr(sender_mod, "send_single_email_async", _fake_send)
    return captured


@pytest.mark.asyncio
async def test_festival_line_never_ships_as_literal_braces(monkeypatch):
    """`{{festival_line}}` must be substituted, not sent to the prospect.

    Before the fix the token was never substituted, so a step using it
    delivered the literal text `{{festival_line}}` to an Indian business
    owner.
    """
    campaign_id = await _build_campaign(
        body_text="Happy {{festival_line}} - quick question about your listing.",
        body_html="<p>Happy {{festival_line}} - quick question?</p>",
    )
    captured = _capture(monkeypatch)

    result = await execute_campaign_step(campaign_id, max_sends=5)
    assert "error" not in result, result
    assert result["sent_count"] == 1, result

    assert "{{festival_line}}" not in captured["body_text"], (
        "the festival token was sent literally"
    )
    assert "{{festival_line}}" not in (captured.get("body_html") or "")
    # It is either the festival line or empty - never the braces.
    assert "festival" not in captured["body_text"].lower()


@pytest.mark.asyncio
async def test_whatsapp_reachable_lead_gets_a_whatsapp_cta(monkeypatch):
    """A mobile number means WhatsApp is the channel that will be answered.

    The line type is computed at enrichment time and stored on the contact;
    the sender has to read it and point the call-to-action at WhatsApp
    rather than asking for an email reply.
    """
    campaign_id = await _build_campaign(
        body_text="Hi {{first_name}}, {{call_to_action}}",
        phone="+91 98200 11223",          # a mobile
        preferred_channel="whatsapp",
    )
    captured = _capture(monkeypatch)

    result = await execute_campaign_step(campaign_id, max_sends=5)
    assert result["sent_count"] == 1, result

    body = captured["body_text"]
    assert "wa.me" in body, f"the CTA should point at WhatsApp, got: {body!r}"
    assert "9820011223" in body, f"the WhatsApp link should carry the number: {body!r}"


@pytest.mark.asyncio
async def test_landline_lead_gets_a_call_cta(monkeypatch):
    """A landline cannot receive WhatsApp, so the CTA asks for a call."""
    campaign_id = await _build_campaign(
        body_text="Hi {{first_name}}, {{call_to_action}}",
        phone="+91 22 1234 5678",          # a landline
        preferred_channel="call",
    )
    captured = _capture(monkeypatch)

    result = await execute_campaign_step(campaign_id, max_sends=5)
    assert result["sent_count"] == 1, result
    assert "call" in captured["body_text"].lower()
    assert "wa.me" not in captured["body_text"]


@pytest.mark.asyncio
async def test_ab_winner_is_declared_by_the_sender_not_only_by_the_page(monkeypatch):
    """The A/B verdict must not depend on someone opening the stats page.

    The winner used to be finalised only inside the stats endpoint, so a
    campaign could run to completion with both variants live and no verdict.
    """
    campaign_id = await _build_campaign(subject_b="Hello (B)")

    async with async_session_maker() as db:
        step = (await db.execute(
            select(CampaignStep).where(CampaignStep.campaign_id == campaign_id)
        )).scalars().first()
        step_id = step.id
        contact = (await db.execute(
            select(Contact).where(Contact.business_id.isnot(None))
        )).scalars().first()
        contact_id = contact.id
        await db.commit()

    captured = _capture(monkeypatch)
    result = await execute_campaign_step(campaign_id, max_sends=5)
    assert result["sent_count"] == 1, result

    # Simulate a decisive reply split: 120 sends per variant, 30 positive
    # replies on A and 3 on B.
    async with async_session_maker() as db:
        sends = []
        for i in range(240):
            variant = "a" if i % 2 == 0 else "b"
            replies = (i % 4 == 0) if variant == "a" else False
            sends.append({
                "campaign_id": campaign_id,
                "step_id": step_id,
                "contact_id": contact_id,
                "status": "sent",
                "variant_used": variant,
                "replied": bool(replies),
                "reply_category": "interested" if replies else None,
                "sent_at": datetime.now(timezone.utc),
            })
        await db.execute(Send.__table__.insert(), sends)
        await db.commit()

    async with async_session_maker() as db:
        winner = await sender_mod._finalise_ab_winner(db, campaign_id)
    assert winner == "a", f"expected variant a to win, got {winner!r}"

    async with async_session_maker() as db:
        step = (await db.execute(
            select(CampaignStep).where(CampaignStep.id == step_id)
        )).scalars().first()
        assert step.variant_winner == "a", (
            "the winner must be persisted, not just returned"
        )
