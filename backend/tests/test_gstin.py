"""GSTIN and Udyam - the identifiers an Indian business is registered under.

Neither Apollo nor any Western directory knows what these are. The
GSTIN's first two digits are the *registered* state, which is a stronger
location signal than a free-text address, and the number's presence says
the business is a registered entity rather than an unlisted one.
"""

import pytest

from app.locations.gstin import (
    extract_gstin,
    extract_udyam,
    gstin_state,
    normalise_gstin,
    state_matches_gstin,
    udyam_state,
)


@pytest.mark.parametrize("text,expected", [
    ("GSTIN: 24AAECS1234B1Z9", "24AAECS1234B1Z9"),
    ("Our GSTIN is 27ABCDE1234F1Z5.", "27ABCDE1234F1Z5"),
    ("gstin 29AAECS1234B1Z9", "29AAECS1234B1Z9"),
    ("27AAACI4403L1ZO", "27AAACI4403L1ZO"),
])
def test_a_gstin_is_found(text, expected):
    assert extract_gstin(text) == expected


def test_a_number_that_is_not_a_gstin_is_not_treated_as_one():
    """The 14th character is always Z; anything else is not a GSTIN."""
    assert extract_gstin("27ABCDE1234F1Y5") is None
    assert extract_gstin("just some long number 123456789012345") is None
    assert extract_gstin("no numbers here") is None
    assert extract_gstin("") is None
    assert extract_gstin(None) is None


def test_the_gstin_carries_the_registered_state():
    """The first two digits are the GST state code."""
    assert gstin_state("27ABCDE1234F1Z5") == "Maharashtra"
    assert gstin_state("24AAECS1234B1Z9") == "Gujarat"
    assert gstin_state("29AAECS1234B1Z9") == "Karnataka"
    assert gstin_state("07AAECS1234B1Z9") == "Delhi"
    assert gstin_state(None) is None
    assert gstin_state("nonsense") is None


def test_an_udyam_registration_is_found():
    assert extract_udyam("Udyam Registration: UDYAM-27-0198288-000000") == (
        "UDYAM-27-0198288-000000"
    )
    assert extract_udyam("Udyam: UDYAM 29 0198288 000000") == "UDYAM290198288000000"
    assert extract_udyam("no registration") is None


def test_an_udyam_number_carries_the_state_too():
    """Two independent signals about where the business is registered."""
    assert udyam_state("UDYAM-27-0198288-000000") == "Maharashtra"
    assert udyam_state("UDYAM-24-0012345-000000") == "Gujarat"
    assert udyam_state(None) is None


def test_a_mismatch_between_the_address_state_and_the_gstin_is_visible():
    """A mismatch is a real signal - a branch office, a business registered
    elsewhere - and silently preferring one over the other would hide it."""
    assert state_matches_gstin("Maharashtra", "27ABCDE1234F1Z5") is True
    assert state_matches_gstin("Gujarat", "27ABCDE1234F1Z5") is False
    # "New Delhi" and "Delhi" are the same state under the GST scheme.
    assert state_matches_gstin("New Delhi", "07AAECS1234B1Z9") is True
    assert state_matches_gstin(None, "27ABCDE1234F1Z5") is False
    assert state_matches_gstin("Maharashtra", None) is False


def test_normalise_gstin():
    assert normalise_gstin(" 27abcde1234f1z5 ") == "27ABCDE1234F1Z5"
    assert normalise_gstin("too short") is None
    assert normalise_gstin(None) is None


def test_the_company_profile_reads_the_registrations_off_a_page():
    from app.enricher.seniority import extract_company_profile

    html = """
    <html><body>
      <footer>
        <p>GSTIN: 24AAECS1234B1Z9</p>
        <p>Udyam Registration: UDYAM-24-0198288-000000</p>
      </footer>
    </body></html>
    """
    profile = extract_company_profile(html)
    assert profile["gstin"] == "24AAECS1234B1Z9"
    assert profile["gstin_state"] == "Gujarat"
    assert profile["udyam_number"] == "UDYAM-24-0198288-000000"


def test_a_page_without_registrations_reports_none():
    """Nothing is guessed: a blank field is honest, an invented one is not."""
    from app.enricher.seniority import extract_company_profile

    profile = extract_company_profile("<html><body><p>Welcome.</p></body></html>")
    assert "gstin" not in profile
    assert "udyam_number" not in profile
