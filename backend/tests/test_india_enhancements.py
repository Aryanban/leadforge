from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.campaigns.india_advisor import in_quiet_hours, dlt_checklist, check_sender_auth
from app.campaigns.india_copy import festival_context, hinglish_closers, culture_checklist, localize_template
from app.campaigns.engagement import whatsapp_handoff, engagement_summary, has_engaged
from app.qualifier.source_trust import source_trust, trust_score_modifier, annotate_lead
from app.qualifier.scorer import score_lead


# --- india_advisor -----------------------------------------------------------

def test_quiet_hours_ist():
    # 17:00 UTC = 22:30 IST -> quiet
    assert in_quiet_hours(datetime(2026, 1, 1, 17, 0, tzinfo=timezone.utc)) is True
    # 08:30 UTC = 14:00 IST -> not quiet
    assert in_quiet_hours(datetime(2026, 1, 1, 8, 30, tzinfo=timezone.utc)) is False
    # 04:00 UTC = 09:30 IST -> edge: end of quiet window
    assert in_quiet_hours(datetime(2026, 1, 1, 4, 0, tzinfo=timezone.utc)) is False


def test_dlt_checklist_flags_unscrubbed_mobile():
    r = dlt_checklist(["+91 98123 45678", "011-4155 6789", None])
    assert r["numbers"][0]["is_mobile"] is True
    assert r["numbers"][1]["is_landline"] is True
    assert all(n["sms_allowed"] is False for n in r["numbers"])
    assert any("DND-scrubbed" in w for w in r["warnings"])


def test_sender_auth_detects_good_domain(monkeypatch):
    # Mock DNS: gmail publishes SPF+DKIM+DMARC.
    records = {
        "gmail.com": ["v=spf1 include:_spf.google.com ~all"],
        "google._domainkey.gmail.com": ["v=DKIM1; k=rsa; p=xxx"],
        "_dmarc.gmail.com": ["v=DMARC1; p=none; rua=mailto:x@google.com"],
    }
    import app.campaigns.india_advisor as ia
    monkeypatch.setattr(ia, "_auth_cache", {})
    monkeypatch.setattr(ia, "_dns_txt", lambda name: records.get(name, []))
    r = ia.check_sender_auth("gmail.com")
    assert r == {"domain": "gmail.com", "spf_ok": True, "dkim_ok": True,
                 "dmarc_ok": True, "ok": True, "warnings": []}


def test_sender_auth_flags_bare_domain(monkeypatch):
    import app.campaigns.india_advisor as ia
    monkeypatch.setattr(ia, "_auth_cache", {})
    monkeypatch.setattr(ia, "_dns_txt", lambda name: [])
    r = ia.check_sender_auth("acme.in")
    assert r["ok"] is False
    assert len(r["warnings"]) == 3  # SPF, DKIM, DMARC


# --- india_copy --------------------------------------------------------------

def test_festival_window_diwali():
    # Mid-window date (Oct 20) falls inside Diwali's tolerant window.
    ctx = festival_context(date(2026, 10, 20))
    assert ctx["festival"] == "Diwali"
    assert "Diwali" in ctx["subject_hook"]


def test_festival_none_out_of_window():
    ctx = festival_context(date(2026, 7, 4))
    assert ctx["festival"] is None


def test_new_year_window_crosses_year():
    # Jan 2 sits in the Dec 28 - Jan 5 window.
    assert festival_context(date(2026, 1, 2))["festival"] == "New Year"


def test_hinglish_and_checklist_shape():
    closers = hinglish_closers()
    assert closers and {"english", "hinglish"} <= set(closers[0].keys())
    kit = culture_checklist()
    assert kit["do"] and kit["dont"]


def test_localize_template_out_of_window_keeps_body():
    out = localize_template("Happy {{festival_line}}!", today=date(2026, 7, 4))
    assert out == "Happy !"  # July: no festival line
    out = localize_template("Happy {{festival_line}}!", today=date(2026, 10, 20))
    assert "Diwali" in out  # in-window: hook offered, operator can delete it


# --- engagement / warm handoff ----------------------------------------------

def _send(**kw):
    base = dict(status="sent", opened=False, clicked=False, replied=False, bounced=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_handoff_requires_engagement():
    sends = [_send(opened=True)] * 2
    assert whatsapp_handoff(sends, True)["suggest"] is False
    sends = [_send(opened=True)] * 3
    assert whatsapp_handoff(sends, True)["suggest"] is True


def test_handoff_needs_mobile_and_unsub_not_checked_here():
    sends = [_send(clicked=True)]
    assert whatsapp_handoff(sends, False)["suggest"] is False
    assert whatsapp_handoff(sends, True)["reason"] == "clicked"


def test_engagement_summary_counts():
    s = engagement_summary([_send(), _send(opened=True, replied=True), _send(bounced=True)])
    assert s == {"sent": 3, "opened": 1, "clicked": 0, "replied": 1, "bounced": 1}


# --- source trust ------------------------------------------------------------

def test_trust_known_sources():
    assert source_trust("google_maps")[0] >= 0.9
    assert source_trust("justdial")[0] <= 0.55
    assert source_trust(None)[0] == 0.70  # default


def test_trust_modifier_bounds():
    assert trust_score_modifier(1.0) == 5.0
    assert trust_score_modifier(0.0) == -8.0
    assert trust_score_modifier(0.70) > 0  # default nudges slightly up


def test_annotate_lead_dict():
    out = annotate_lead({"name": "X", "source": "justdial"})
    assert out["source_trust"] == 0.50
    assert out["trust_modifier"] < 0
    assert out["name"] == "X"


def test_scorer_source_trust_overlay():
    base = {"name": "Ramesh Traders", "phone": "+919812345678",
            "website": "https://ramesh.in", "rating": 4.8, "reviews_count": 30}
    plain = score_lead(dict(base))
    maps = score_lead(dict(base, source="google_maps"))
    jd = score_lead(dict(base, source="justdial"))
    assert maps["score"] > plain["score"]
    assert jd["score"] < plain["score"]
    assert any("directory-sourced" in b for b in jd["badges"])


def test_scorer_legacy_score_unchanged_without_source():
    business = {
        "name": "Top Realtors", "phone": "+91 98765 43210",
        "website": "https://toprealtors.in", "rating": 4.9, "reviews_count": 25,
    }
    contacts = [{"email": "contact@toprealtors.in", "is_verified": True}]
    r = score_lead(business, contacts)
    assert r["score"] >= 80 and r["tier"] == "HOT"
    assert r["source_trust"] is None
    assert "Verified Email" in r["badges"]
