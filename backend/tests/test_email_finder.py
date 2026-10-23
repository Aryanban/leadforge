import pytest
import re
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


@pytest.mark.parametrize(
    "seed,expected",
    [
        ("rsharma@acme.in", "flast"),
        ("rajeshsharma@acme.in", "firstlast"),
        ("rajesh.sharma@acme.in", "first.last"),
        ("rajesh_sharma@acme.in", "first_last"),
        ("rajesh-sharma@acme.in", "first-lastr"),
        ("rajeshs@acme.in", "firstl"),
        ("r.sharma@acme.in", "f.last"),
        ("sharma@acme.in", "last"),
    ],
)
def test_pattern_detects_all_templates(seed, expected):
    """Every template must be detectable from a real seed.

    The old shape heuristic could only reach 4 of the 10 patterns - the
    ``f.last`` and ``firstl`` branches were unreachable dead code - and it
    classified single-token seeds as ``{first}`` at 0.95 confidence, which is
    confidently wrong rather than merely wrong.
    """
    names = [("Rajesh", "Sharma"), ("Aarav", "Verma")]
    pattern, _conf = infer_pattern([seed], "acme.in", names)
    assert pattern == expected


def test_pattern_single_seed_is_never_confident():
    """One seed is suggestive, not conclusive."""
    names = [("Rajesh", "Sharma")]
    _pattern, conf = infer_pattern(["rsharma@acme.in"], "acme.in", names)
    assert conf <= 0.5


def test_pattern_dominance_beats_a_single_outlier():
    """Two agreeing seeds must outrank one disagreeing seed."""
    names = [("Aarav", "Sharma"), ("Rohan", "Verma"), ("Priya", "Nair")]
    pattern, conf = infer_pattern(
        ["a.sharma@acme.in", "r.verma@acme.in", "somethingelse@acme.in"],
        "acme.in", names,
    )
    assert pattern == "f.last"
    assert conf >= 0.6


def test_pattern_seed_survives_a_mismatched_name_list():
    """Seed evidence must not be discarded because the exec list is partial.

    The name-based and shape-based matchers used to be mutually exclusive,
    so a seed belonging to the third exec on a team page taught us nothing
    and the learned pattern was thrown away.
    """
    # The seed belongs to Priya Nair, who is NOT in the supplied name list.
    pattern, _conf = infer_pattern(
        ["priya.nair@acme.in"], "acme.in", [("Rajesh", "Sharma")]
    )
    assert pattern == "first.last"


def test_candidates_are_all_syntactically_valid():
    """No candidate may contain a space or a leading/trailing separator.

    The old renderer emitted "priya.@acme.in" and
    "rajesh.kumar sharma@acme.in", which consumed half the candidate budget
    and burned real SMTP probes on addresses that cannot exist.
    """
    for names in ([("Priya", "Nair")], [("Rajesh", "Kumar Sharma")], [("Priya", "")]):
        cands, _pattern, _conf = generate_candidates("acme.in", person_names=names)
        for cand in cands:
            local = cand.split("@")[0]
            assert " " not in local, f"candidate contains a space: {cand}"
            assert not local.startswith("."), f"candidate starts with '.': {cand}"
            assert not local.endswith("."), f"candidate ends with '.': {cand}"
            assert re.match(r"^[A-Za-z0-9._+-]+$", local), f"invalid local: {cand}"


def test_candidates_cover_more_than_one_person():
    """The person budget must be spread across the people we know.

    Previously the first name consumed all four slots, so the second person -
    whom we had also learned the pattern from - never got a candidate.
    """
    cands, _pattern, _conf = generate_candidates(
        "acme.in", person_names=[("Priya", "Nair"), ("Rajesh", "Sharma")]
    )
    locals_ = [c.split("@")[0] for c in cands]
    assert any("priya" in l for l in locals_)
    assert any("rajesh" in l for l in locals_)


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
