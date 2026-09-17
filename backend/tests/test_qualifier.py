from types import SimpleNamespace
from typing import Any, Dict, List

from app.qualifier.nl_icp import parse_icp_text
from app.qualifier.ranker import rank_businesses
from app.qualifier.scorer import PRESETS, score_lead


def make_business(**overrides) -> Any:
    base: Dict[str, Any] = {
        "id": 1,
        "name": "Balaji Properties & Developers",
        "phone": "+91 98112 34567",
        "website": "https://balajiproperties.example.in",
        "address": "Sector 8, Rohini, New Delhi",
        "rating": 4.8,
        "reviews_count": 84,
        "industry": "Real Estate Agency",
        "latitude": 28.73,
        "longitude": 77.09,
        "maps_url": None,
        "source": "test",
        "extra_data": {"is_claimed": True},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_contact(**overrides) -> Any:
    base: Dict[str, Any] = {
        "id": 1,
        "first_name": "Rajesh",
        "last_name": "Sharma",
        "title": "Principal Broker",
        "email": "rajesh@balajiproperties.example.in",
        "phone": "+91 98112 34567",
        "is_verified": True,
        "whatsapp_link": "https://wa.me/919811234567",
        "social_links": None,
        "verification_status": "valid",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_icp(**overrides) -> Any:
    base: Dict[str, Any] = {
        "niche": "Real Estate",
        "preset": "outreach_quality",
        "min_score": 45,
        "signal_weights": None,
        "keywords": None,
        "exclude_keywords": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_score_lead_matches_legacy_formula():
    """Without an ICP profile the weighted model reproduces the legacy scores."""
    full = score_lead(make_business(), [make_contact()])
    assert full["score"] == 95  # 30 + 15 + 15 + 15 + 10 + 10
    assert full["tier"] == "HOT"
    assert "Verified Email" in full["badges"]
    assert "Top Rated" in full["badges"]
    assert "High Reviews" in full["badges"]

    empty = score_lead(make_business(phone=None, website=None, rating=None, reviews_count=None), [])
    assert empty["score"] == 10
    assert empty["tier"] == "COLD"


def test_score_lead_unverified_email_uses_lower_weight():
    result = score_lead(
        make_business(rating=4.2, reviews_count=5),
        [make_contact(is_verified=False)],
    )
    assert result["score"] == 15 + 15 + 15 + 15 + 5 + 5  # 70


def test_score_lead_unclaimed_badge_without_icp():
    business = make_business(extra_data={"is_claimed": False})
    result = score_lead(business, [make_contact()])
    assert "Unclaimed GBP" in result["badges"]


def test_icp_unlocks_extra_signals():
    business = make_business(
        extra_data={
            "is_claimed": False,
            "ssl_valid": True,
            "site_stale": False,
            "running_ads": True,
        }
    )
    contacts = [make_contact(social_links={"instagram": "https://instagram.com/x"})]

    result = score_lead(business, contacts, make_icp())
    assert result["score"] == 100  # 95 legacy + 8 + 6 + 4 + 4 + 6, clamped
    assert result["signal_breakdown"]["unclaimed_gbp"] == PRESETS["outreach_quality"]["unclaimed_gbp"]
    assert result["signal_breakdown"]["running_ads"] == PRESETS["outreach_quality"]["running_ads"]
    assert "Niche Match" in result["badges"]


def test_agency_preset_flips_stale_website_into_opportunity():
    business = make_business(
        rating=3.9,
        reviews_count=2,
        extra_data={"is_claimed": False, "ssl_valid": False, "site_stale": True, "running_ads": False},
    )
    contacts = [make_contact()]
    outreach = score_lead(business, contacts, make_icp(preset="outreach_quality"))
    agency = score_lead(business, contacts, make_icp(preset="agency_opportunity"))

    assert outreach["signal_breakdown"]["site_stale"] < 0
    assert agency["signal_breakdown"]["site_stale"] > 0
    assert agency["score"] > outreach["score"]


def test_signal_weight_override():
    icp = make_icp(signal_weights={"running_ads": 25})
    business = make_business(extra_data={"running_ads": True})
    result = score_lead(business, [make_contact()], icp)
    assert result["signal_breakdown"]["running_ads"] == 25


def test_category_match_requires_niche_overlap():
    no_match = score_lead(make_business(), [make_contact()], make_icp(niche="Dental Clinic"))
    assert "Niche Match" not in no_match["badges"]


def test_parse_icp_text_basic():
    parsed = parse_icp_text("Dentists in South Delhi with verified emails")
    assert parsed["niche"].lower().startswith("dentist")
    assert parsed["area"] == "South Delhi"
    assert parsed["min_score"] == 60
    assert parsed["preset"] == "outreach_quality"


def test_parse_icp_text_agency_angle():
    parsed = parse_icp_text("plumbers near Connaught Place with no website")
    assert parsed["preset"] == "agency_opportunity"
    assert parsed["area"] == "Connaught Place"
    assert "website" in parsed["exclude_keywords"]


def test_parse_icp_text_high_intent():
    parsed = parse_icp_text("Best leads: dental clinics in Delhi")
    assert parsed["min_score"] == 70


def test_rank_businesses_applies_min_score_and_ordering():
    hot = make_business(name="Hot Lead", icp_profile_id=1)
    cold = make_business(name="Cold Lead", phone=None, website=None, rating=None, reviews_count=None)
    contacts = {1: [make_contact()], 2: []}

    icp = make_icp(min_score=60)
    ranked = rank_businesses([hot, cold], contacts, icp, limit=10)

    assert len(ranked) == 1
    assert ranked[0]["name"] == "Hot Lead"
    assert ranked[0]["score"] >= 60


def test_rank_businesses_keyword_filter():
    business = make_business(name="Smile Dental Clinic")
    icp = make_icp(min_score=0, keywords=["dental"])
    ranked = rank_businesses([business], {1: [make_contact()]}, icp)
    assert len(ranked) == 1

    icp_excluded = make_icp(min_score=0, exclude_keywords=["dental"])
    ranked = rank_businesses([business], {1: [make_contact()]}, icp_excluded)
    assert len(ranked) == 0
