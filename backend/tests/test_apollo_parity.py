"""Tests for the Apollo-parity surface: reply categorisation, A/B winner
selection, saved lists, suppression API, timeseries, and the launch guard.

Offline-only: no IMAP, no SMTP, no network — pure logic plus FastAPI
TestClient against the shared test database from conftest.
"""

import pytest
from httpx import AsyncClient

from app.campaigns.reply_poller import (
    categorize_reply,
    derive_imap_host,
    authored_text,
    thread_references,
)
from app.api.campaigns import decide_ab_winner
from app.main import app


@pytest.fixture
async def client():
    """Async test client against the FastAPI app (same pattern as
    tests/test_leads_api.py, which has no shared client fixture)."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# --- reply categorisation (rules that protect suppression) -------------------

def test_derive_imap_host_swaps_smtp_prefix():
    assert derive_imap_host("smtp.gmail.com") == "imap.gmail.com"
    assert derive_imap_host("smtp.example.co.uk") == "imap.example.co.uk"
    assert derive_imap_host(None) is None
    assert derive_imap_host("") is None


def test_interested_beats_soft_no_ordering():
    cat, opt_out = categorize_reply("Re: hi", "I'm interested, call me Tuesday")
    assert cat == "interested" and opt_out is False


def test_not_interested_not_read_as_interested():
    # "not interested" contains "interested" — negative must win.
    cat, opt_out = categorize_reply("Re: hi", "Not interested right now, sorry")
    assert cat == "not_interested" and opt_out is False


def test_bare_stop_suppresses():
    cat, opt_out = categorize_reply("Re: Quick question about {{business_name}}", "STOP.")
    assert cat == "opt_out" and opt_out is True


def test_unsubscribe_in_body_suppresses():
    cat, opt_out = categorize_reply("Re: hi", "please unsubscribe me")
    assert cat == "opt_out" and opt_out is True


def test_our_own_footer_does_not_make_a_reply_an_opt_out():
    cat, opt_out = categorize_reply(
        "Re: hi", "Yes! Let's talk.\n\nTo stop receiving these emails: http://x/y")
    assert cat != "opt_out" and opt_out is False


def test_out_of_office_detected():
    cat, opt_out = categorize_reply("Re: hi", "I am out of office until Monday")
    assert cat == "out_of_office" and opt_out is False


def test_autoreply_header_wins():
    cat, opt_out = categorize_reply("Re: hi", "anything", {"Auto-Submitted": "auto-reply"})
    assert cat == "out_of_office"


def test_neutral_reply_is_other():
    cat, opt_out = categorize_reply("Re: hi", "Who is this?")
    assert cat == "other" and opt_out is False


def test_authored_text_strips_footer_and_quote():
    body = "Hi there,\nthis is my reply.\n\nTo stop receiving these emails: http://x/y"
    assert authored_text(body) == "Hi there,\nthis is my reply."


# --- A/B winner selection -----------------------------------------------------

def test_ab_winner_undecided_below_sample():
    assert decide_ab_winner(9, 9, 9, 0) is None


def test_ab_winner_by_reply_rate():
    assert decide_ab_winner(10, 3, 10, 1) == "a"
    assert decide_ab_winner(10, 1, 10, 3) == "b"


def test_ab_tie_stays_undecided():
    assert decide_ab_winner(10, 2, 10, 2) is None


# --- API surface ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeseries_shape(client):
    res = await client.get("/api/v1/analytics/timeseries?days=7")
    assert res.status_code == 200
    body = res.json()
    assert body["period_days"] == 7
    assert len(body["days"]) == 7
    point = body["days"][0]
    assert set(point) == {"date", "sent", "opened", "replied", "bounced"}


@pytest.mark.asyncio
async def test_tasks_shape(client):
    res = await client.get("/api/v1/analytics/tasks")
    assert res.status_code == 200
    for t in res.json()["tasks"]:
        assert {"key", "label", "count", "severity", "href"} <= set(t)


@pytest.mark.asyncio
async def test_saved_lists_crud(client):
    created = await client.post("/api/v1/lists", json={"name": "Hot dentists", "filters": {"has_email": True}})
    assert created.status_code == 200
    list_id = created.json()["id"]
    listed = await client.get("/api/v1/lists")
    assert any(l["id"] == list_id for l in listed.json())
    deleted = await client.delete(f"/api/v1/lists/{list_id}")
    assert deleted.status_code == 200
    assert all(l["id"] != list_id for l in (await client.get("/api/v1/lists")).json())


@pytest.mark.asyncio
async def test_suppression_api_add_and_list(client):
    res = await client.post("/api/v1/suppression", json={"identifier": "block@example.test", "reason": "manual"})
    assert res.status_code == 200
    assert res.json()["added"] is True
    listed = await client.get("/api/v1/suppression?active_only=true")
    assert any(i["identifier"] == "block@example.test" for i in listed.json()["items"])


@pytest.mark.asyncio
async def test_suppression_domain_requires_at(client):
    res = await client.post("/api/v1/suppression", json={"identifier": "example.com", "reason": "manual", "domain_wide": True})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_inbox_empty_state(client):
    res = await client.get("/api/v1/inbox")
    assert res.status_code == 200
    body = res.json()
    assert body["items"] == []
    assert set(body["counts"]) == {"interested", "not_interested", "opt_out", "out_of_office", "other"}


@pytest.mark.asyncio
async def test_launch_refuses_without_targets(client):
    camp = await client.post("/api/v1/campaigns/", json={
        "name": "No recipients",
        "steps": [{"subject": "Hi", "body_text": "Body"}],
    })
    cid = camp.json()["id"]
    res = await client.post(f"/api/v1/campaigns/{cid}/launch")
    assert res.status_code == 400
    assert "recipients" in res.json()["detail"]


@pytest.mark.asyncio
async def test_step_stats_and_ab_creation(client):
    camp = await client.post("/api/v1/campaigns/", json={
        "name": "AB sequence",
        "steps": [{"subject": "A subject", "subject_b": "B subject", "body_text": "Body"}],
    })
    cid = camp.json()["id"]
    res = await client.get(f"/api/v1/campaigns/{cid}/step-stats")
    assert res.status_code == 200
    step = res.json()["steps"][0]
    assert step["subject_b"] == "B subject"
    assert step["variants"]["winner"] is None


@pytest.mark.asyncio
async def test_lead_detail_and_suppress(client):
    lead = await client.post("/api/v1/leads/", json={"name": "Detail Co"})
    bid = lead.json()["id"]
    detail = await client.get(f"/api/v1/leads/{bid}/detail")
    assert detail.status_code == 200
    assert set(detail.json()) == {"business", "contacts", "timeline"}
    res = await client.post(f"/api/v1/leads/{bid}/suppress")
    assert res.status_code == 200
    assert res.json()["business_id"] == bid
