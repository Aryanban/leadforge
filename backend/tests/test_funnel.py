"""The funnel: where the pipeline leaks.

The dashboard used to show four flat counters, which cannot answer the
only question that matters: which stage is losing the leads. These tests
pin the numbers to the data, so the funnel cannot drift into telling the
operator a comforting lie.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.campaign_step import CampaignStep
from app.models.contact import Contact
from app.models.mailbox import Mailbox
from app.models.send import Send


async def _seed_funnel_world():
    """Three businesses at three different stages of the pipeline."""
    async with async_session_maker() as db:
        with_phone = Business(
            name="Phone Only Traders", industry="Traders", phone="+91 98111 00001",
        )
        with_email = Business(
            name="Email Traders", industry="Traders", phone="+91 98111 00002",
            website="https://email.example.in",
        )
        reached = Business(
            name="Reached Traders", industry="Traders", phone="+91 98111 00003",
            website="https://reached.example.in",
        )
        db.add_all([with_phone, with_email, reached])
        await db.flush()

        db.add_all([
            # A business-level contact: a phone, no email.
            Contact(
                business_id=with_phone.id, phone="+91 98111 00001",
                preferred_channel="whatsapp", verification_status="unverified",
            ),
            # An email that was never verified.
            Contact(
                business_id=with_email.id, email="hello@email.example.in",
                phone="+91 98111 00002", verification_status="valid",
                is_verified=False,
            ),
            # A verified email that was sent to and opened.
            Contact(
                business_id=reached.id, email="boss@reached.example.in",
                phone="+91 98111 00003", verification_status="valid",
                is_verified=True, person_identified=True, first_name="Boss",
            ),
        ])

        campaign = Campaign(name="Funnel Test", status="active")
        db.add(campaign)
        await db.flush()
        step = CampaignStep(
            campaign_id=campaign.id, step_number=1, subject="Hello",
            body_text="Hi", delay_days=0,
        )
        db.add(step)
        await db.flush()
        mailbox = Mailbox(
            email="sender@example.in", password="x", smtp_host="smtp.example.in",
            smtp_port=587, daily_limit=10, sent_today=0,
        )
        db.add(mailbox)
        await db.flush()

        contact = (await db.execute(
            select(Contact).where(Contact.business_id == reached.id)
        )).scalar_one()
        db.add(Send(
            campaign_id=campaign.id, step_id=step.id, contact_id=contact.id,
            mailbox_id=mailbox.id, status="sent", opened=True, replied=True,
            reply_category="interested", variant_used="a",
        ))
        await db.commit()


@pytest.mark.asyncio
async def test_the_funnel_counts_each_stage_from_the_data():
    from app.api.analytics import get_funnel

    await _seed_funnel_world()
    async with async_session_maker() as db:
        funnel = await get_funnel(days=90, include_demo=True, db=db)

    stages = {s["key"]: s["count"] for s in funnel["stages"]}
    assert stages["discovered"] == 3
    assert stages["phone"] == 3
    assert stages["email"] == 2
    assert stages["verified"] == 1
    assert stages["sent"] == 1
    assert stages["opened"] == 1
    assert stages["replied"] == 1
    assert stages["positive"] == 1


@pytest.mark.asyncio
async def test_the_funnel_is_a_funnel_each_stage_narrows():
    """A stage that exceeds the one before it means the counting is wrong."""
    from app.api.analytics import get_funnel

    await _seed_funnel_world()
    async with async_session_maker() as db:
        funnel = await get_funnel(days=90, include_demo=True, db=db)

    stages = funnel["stages"]
    for i in range(1, len(stages)):
        if stages[i]["key"] == "targeted":
            # A business can be in two campaigns, so this one is not a
            # strict narrowing of the stage above it.
            continue
        assert stages[i]["count"] <= stages[i - 1]["count"], (
            f"{stages[i]['key']} ({stages[i]['count']}) exceeds "
            f"{stages[i - 1]['key']} ({stages[i - 1]['count']})"
        )


@pytest.mark.asyncio
async def test_the_funnel_reports_the_per_mailbox_breakdown():
    from app.api.analytics import get_funnel

    await _seed_funnel_world()
    async with async_session_maker() as db:
        funnel = await get_funnel(days=90, include_demo=True, db=db)

    assert funnel["by_mailbox"], "a mailbox that sent should be reported"
    row = funnel["by_mailbox"][0]
    assert row["email"] == "sender@example.in"
    assert row["sent"] == 1
    assert row["opened"] == 1
    assert row["replied"] == 1
    assert row["reply_rate"] == 100.0


@pytest.mark.asyncio
async def test_the_funnel_reports_reply_categories():
    from app.api.analytics import get_funnel

    await _seed_funnel_world()
    async with async_session_maker() as db:
        funnel = await get_funnel(days=90, include_demo=True, db=db)

    categories = {c["category"]: c["count"] for c in funnel["reply_categories"]}
    assert categories.get("interested") == 1
