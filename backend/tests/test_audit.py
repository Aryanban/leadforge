"""The audit log.

"Which decisions did the product make, and why?" - the question an
operator asks when a campaign underperforms. The log is only worth
having if the decisions are actually recorded, and if the summary reads
like a sentence rather than a code.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.models.audit_event import EVENTS, AuditEvent


@pytest.mark.asyncio
async def test_an_event_is_recorded_and_read_back():
    from app.models.audit_event import record

    async with async_session_maker() as db:
        await record(
            db,
            "email_sent",
            "Emailed owner@example.in at Acme Realty",
            entity_type="contact",
            entity_id=42,
            detail={"campaign_id": 7},
        )
        await db.commit()

    from app.api.audit import list_audit_events

    async with async_session_maker() as db:
        result = await list_audit_events(limit=10, offset=0, event_type=None,
                                        entity_type=None, entity_id=None, db=db)

    assert result["total"] == 1
    event = result["events"][0]
    assert event["event_type"] == "email_sent"
    assert event["entity_type"] == "contact"
    assert event["entity_id"] == 42
    assert event["detail"] == {"campaign_id": 7}
    # The summary is a sentence a human can read.
    assert "owner@example.in" in event["summary"]
    assert event["event_label"] == EVENTS["email_sent"]


@pytest.mark.asyncio
async def test_the_feed_filters_by_event_type():
    from app.models.audit_event import record
    from app.api.audit import list_audit_events

    async with async_session_maker() as db:
        await record(db, "email_sent", "Sent one")
        await record(db, "email_bounced", "Bounced one")
        await record(db, "email_bounced", "Bounced another")
        await db.commit()

    async with async_session_maker() as db:
        sent = await list_audit_events(limit=10, offset=0, event_type="email_sent",
                                       entity_type=None, entity_id=None, db=db)
        bounced = await list_audit_events(limit=10, offset=0, event_type="email_bounced",
                                          entity_type=None, entity_id=None, db=db)

    assert sent["total"] == 1
    assert bounced["total"] == 2
    # Newest first.
    assert bounced["events"][0]["summary"] == "Bounced another"


@pytest.mark.asyncio
async def test_the_feed_filters_by_entity():
    from app.models.audit_event import record
    from app.api.audit import list_audit_events

    async with async_session_maker() as db:
        await record(db, "email_sent", "One", entity_type="contact", entity_id=1)
        await record(db, "email_sent", "Two", entity_type="contact", entity_id=2)
        await record(db, "campaign_launched", "Three", entity_type="campaign", entity_id=1)
        await db.commit()

    async with async_session_maker() as db:
        contact_one = await list_audit_events(
            limit=10, offset=0, event_type=None, entity_type="contact",
            entity_id=1, db=db
        )
        everything = await list_audit_events(
            limit=10, offset=0, event_type=None, entity_type=None,
            entity_id=None, db=db
        )

    assert contact_one["total"] == 1
    assert contact_one["events"][0]["summary"] == "One"
    assert everything["total"] == 3


@pytest.mark.asyncio
async def test_the_event_vocabulary_is_discoverable():
    """A filter list built from the vocabulary can be discovered; one built
    from a hard-coded array in the UI cannot."""
    from app.api.audit import audit_event_types

    async with async_session_maker() as db:
        result = await audit_event_types(db=db)

    types = {t["event_type"]: t for t in result["types"]}
    assert "email_sent" in types
    assert types["email_sent"]["label"]
    assert "count" in types["email_sent"]


@pytest.mark.asyncio
async def test_recording_never_breaks_the_action_it_audits():
    """An audit failure must not fail the send."""
    from app.models.audit_event import record

    class _Broken:
        def add(self, _obj):
            raise RuntimeError("audit table is gone")

    async with async_session_maker() as db:
        # Does not raise.
        await record(_Broken(), "email_sent", "Should not raise")
