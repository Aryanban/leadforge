import pytest
from app.enricher.email_finder import generate_email_permutations, calculate_lead_quality_score
from app.enricher.pattern import infer_pattern, generate_candidates, match_pattern


def test_generate_email_permutations_with_full_name():
    # Legacy shim: person-name permutations still work for old call sites.
    perms = generate_email_permutations("Rajesh Sharma", "example.com")
    assert "rajesh.sharma@example.com" in perms
    assert "rajesh@example.com" in perms
    assert "rsharma@example.com" in perms
    assert "contact@example.com" in perms
    assert "sales@example.com" in perms

def test_generate_email_permutations_with_business_name():
    perms = generate_email_permutations("Apex Realty Solutions Private Limited", "apexrealty.in")
    assert "apex@apexrealty.in" in perms
    assert "info@apexrealty.in" in perms
    assert "contact@apexrealty.in" in perms

def test_pattern_learned_from_seeds_with_names():
    # Two seeds + the people they belong to -> f.last at high confidence.
    names = [("Aarav", "Sharma"), ("Rohan", "Verma")]
    pattern, conf = infer_pattern(
        ["a.sharma@acme.in", "r.verma@acme.in", "info@acme.in"],
        "acme.in", names,
    )
    assert pattern == "f.last"
    assert conf >= 0.8


def test_pattern_ignores_generic_and_foreign_seeds():
    # info@/contact@ teach nothing; other-domain seeds are ignored.
    pattern, conf = infer_pattern(
        ["info@acme.in", "contact@acme.in", "a.sharma@other.com"], "acme.in")
    assert pattern == "first.last"  # honest prior fallback
    assert conf <= 0.3


def test_pattern_gibberish_seed_abstains():
    pattern, conf = infer_pattern(["e65rc109q@acme.in"], "acme.in")
    assert conf <= 0.3


def test_candidates_never_use_company_name():
    cands, _, _ = generate_candidates("acme.in", person_names=[("Priya", "Nair")])
    assert not any("acme" in c.split("@")[0] for c in cands)
    assert "contact@acme.in" in cands  # aliases still appended last


def test_candidates_follow_learned_pattern_first():
    cands, pattern, _ = generate_candidates(
        "acme.in", person_names=[("Priya", "Nair")],
        seeds=["a.sharma@acme.in"],
    )
    _ = pattern
    # Person candidates precede department aliases.
    first_alias = next(i for i, c in enumerate(cands) if c.split("@")[0] in (
        "contact", "info", "sales", "office"))
    assert first_alias >= 1
    assert all("@" in c and c.endswith("@acme.in") for c in cands)


def test_calculate_lead_quality_score_hot_tier():
    business = {
        "name": "Top Realtors",
        "phone": "+91 98765 43210",
        "website": "https://toprealtors.in",
        "rating": 4.9,
        "reviews_count": 25
    }
    contacts = [
        {"email": "contact@toprealtors.in", "is_verified": True}
    ]
    result = calculate_lead_quality_score(business, contacts)
    assert result["score"] >= 80
    assert result["tier"] == "HOT"
    assert "Verified Email" in result["badges"]
    business = {
        "name": "Top Realtors",
        "phone": "+91 98765 43210",
        "website": "https://toprealtors.in",
        "rating": 4.9,
        "reviews_count": 25
    }
    contacts = [
        {"email": "contact@toprealtors.in", "is_verified": True}
    ]
    result = calculate_lead_quality_score(business, contacts)
    assert result["score"] >= 80
    assert result["tier"] == "HOT"
    assert "Verified Email" in result["badges"]

def test_calculate_lead_quality_score_cold_tier():
    business = {
        "name": "Unknown Shop",
        "phone": None,
        "website": None,
        "rating": 2.5,
        "reviews_count": 1
    }
    contacts = []
    result = calculate_lead_quality_score(business, contacts)
    assert result["score"] < 40
    assert result["tier"] == "COLD"
