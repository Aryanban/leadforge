import pytest
from app.verifier.email_status import (
    EmailStatus,
    classify_email,
    detect_disposable,
    detect_free_provider,
    detect_placeholder_domain,
    detect_role_account,
    did_you_mean_domain,
    looks_like_gibberish,
    should_send,
)

# --- status enum ------------------------------------------------------------
def test_status_enum_is_complete():
    """The old code could only express 11 states; the market enum is broader."""
    expected = {
        "valid", "invalid", "catch_all", "catch_all_unknown", "disposable",
        "role_account", "free_email", "greylisted", "unknown", "blocked",
        "syntax_error", "domain_error", "no_mx", "smtp_error", "timeout",
        "spamtrap", "abuse", "do_not_mail", "gibberish", "possible_typo",
    }
    assert {s.value for s in EmailStatus} == expected


# --- role accounts ----------------------------------------------------------
@pytest.mark.parametrize("local", ["info", "sales", "support", "enquiry", "reception"])
def test_role_accounts_detected(local):
    assert detect_role_account(local) is True


@pytest.mark.parametrize("local", ["john", "priya", "rakesh", "info2025x", None, ""])
def test_personal_local_parts_not_role(local):
    assert detect_role_account(local) is False


def test_prefixed_role_variant_detected():
    assert detect_role_account("info.acme") is True


def test_role_account_still_classifies_but_is_not_a_person():
    """Role addresses are legitimate SMB leads, just not 'person found'."""
    result = classify_email("info@acme.in")
    assert result.is_role is True
    # It must not be silently dropped, and must not count as sendable.
    assert result.status == EmailStatus.UNKNOWN
    assert should_send(result) is False


# --- free providers ---------------------------------------------------------
def test_free_providers_include_india_defaults():
    for domain in ("gmail.com", "rediffmail.com", "zohomail.in", "yahoo.co.in"):
        assert detect_free_provider(domain) is True


def test_free_email_is_not_a_rejection_reason():
    """On Indian SMB leads a personal Gmail is the norm, not a defect."""
    result = classify_email("rakesh@gmail.com")
    assert result.is_free is True
    assert result.status not in (EmailStatus.INVALID, EmailStatus.DISPOSABLE)


# --- disposable / placeholder ----------------------------------------------
def test_disposable_detected():
    assert detect_disposable("mailinator.com") is True
    assert classify_email("x@yopmail.com").status == EmailStatus.DISPOSABLE


def test_placeholder_hosts_are_noise():
    assert classify_email("a@sentry.io").sub_status == "placeholder_domain"
    assert classify_email("a@example.com").status == EmailStatus.DOMAIN_ERROR


def test_real_corporate_domain_is_not_treated_as_placeholder():
    """Regression: EXCLUDED_EMAIL_DOMAINS used to drop all @google.com."""
    assert detect_placeholder_domain("google.com") is False
    result = classify_email("employee@google.com")
    assert result.status == EmailStatus.UNKNOWN
    assert result.sub_status == "precheck_passed"


# --- typo detection ---------------------------------------------------------
def test_known_typo_maps_to_canonical():
    assert did_you_mean_domain("gmial.com") == "gmail.com"


def test_typo_is_flagged_not_dropped():
    result = classify_email("bob@gmial.com")
    assert result.status == EmailStatus.POSSIBLE_TYPO
    assert "gmail.com" in result.sub_status


# --- gibberish --------------------------------------------------------------
@pytest.mark.parametrize(
    "local",
    ["e65rc109q", "rakeshkumar2024", "bcdfghjkl", "q9z8x7w6v5"],
)
def test_gibberish_detected(local):
    assert looks_like_gibberish(local) is True


@pytest.mark.parametrize(
    "local",
    ["johndoe", "priya", "smita.sharma", "r.k.sharma", "mohammed",
     "karthik99", "ali2k", "john3"],
)
def test_real_names_not_flagged_as_gibberish(local):
    assert looks_like_gibberish(local) is False


def test_gibberish_surfaces_in_classification():
    assert classify_email("e65rc109q@acme.in").status == EmailStatus.GIBBERISH


# --- syntax -----------------------------------------------------------------
@pytest.mark.parametrize("email", ["", None, "not-an-email", "a@@b.com", "a@b", "a b@c.com"])
def test_malformed_addresses_rejected(email):
    result = classify_email(email)
    assert result.status in (EmailStatus.SYNTAX_ERROR, EmailStatus.INVALID)


# --- never defaults to valid -----------------------------------------------
def test_unknown_never_counts_as_valid():
    """The P0 bug: every SMTP failure used to return (True, 'valid_mx')."""
    result = classify_email("someone@acme.in")
    assert result.is_deliverable is False
    assert result.sendable is False
    assert should_send(result) is False


def test_precheck_passed_low_confidence():
    result = classify_email("someone@acme.in")
    assert result.confidence < 0.5
