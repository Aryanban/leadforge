"""The cold-email linter, for the Indian market.

The word list was Western-only, so an Indian cold email full of "Dear
Sir/Madam", "kindly revert back" and "Sent from my iPhone" scored
"Good" - while the same message read by an Indian recipient is
obviously a list blast. These tests pin the India-aware behaviour, and
the density signals the README promises.
"""

import pytest

from app.campaigns.spam_checker import check_cold_email_spam


def test_a_personalised_indian_email_scores_well():
    """The message the product should be able to send without complaint."""
    result = check_cold_email_spam(
        "Quick question about {{business_name}}",
        "Hi {{first_name}},\n\n"
        "Saw your listing in {{city}} - the {{ai_icebreaker}}\n\n"
        "Would a 4-minute call work this week?\n\nBest,\nAparna",
    )
    assert result["score"] >= 88
    assert result["tier"] == "Excellent"
    assert result["india_risk_phrases"] == []
    assert result["india_tells"] == []
    assert result["mobile_signature"] is None
    assert result["indian_salutation"] is False


def test_the_mobile_signature_is_caught():
    """On its own this is the strongest deliverability signal there is."""
    result = check_cold_email_spam(
        "Quick question",
        "Hi {{first_name}}, quick question about {{business_name}}.\n\nSent from my iPhone",
    )
    assert result["mobile_signature"] == "sent from my iphone"
    assert result["score"] < 88
    assert any("mobile signature" in w for w in result["warnings"])


def test_dear_sir_madam_is_flagged():
    """Unpersonalised, not spam - but the recipient can tell."""
    result = check_cold_email_spam(
        "Business proposal",
        "Dear Sir/Madam,\n\nWe would like to discuss {{business_name}}.\n\nRegards",
    )
    assert result["indian_salutation"] is True
    assert "dear sir/madam" in result["india_tells"]
    assert any("Sir/Madam" in w for w in result["warnings"])


def test_indian_office_phrases_are_flagged_as_tells():
    result = check_cold_email_spam(
        "Request",
        "Dear {{first_name}}, kindly revert back to my query. Do the needful.\n\nThanks & Regards",
    )
    assert "kindly revert" in result["india_tells"] or "revert back" in result["india_tells"]
    assert "do the needful" in result["india_tells"]
    # A tell is not a spam trigger: it must not be reported as one.
    assert "do the needful" not in result["india_risk_phrases"]


def test_indian_spam_phrases_are_spam_triggers():
    """The number-harvesting close and the guaranteed-offer language."""
    result = check_cold_email_spam(
        "Great opportunity",
        "Hi {{first_name}}, save our number and we will call you. "
        "Guaranteed returns and a data entry job from home.\n\nRegards",
    )
    assert "save our number" in result["india_risk_phrases"]
    assert "guaranteed returns" in result["india_risk_phrases"]
    assert result["tier"] == "High Spam Risk"


def test_the_density_signals_exist_and_fire():
    """A ratio catches what a per-word check cannot."""
    shouting = (
        "WE ARE THE BEST IN THE WORLD!!! BUY NOW!!! CLICK NOW!!! "
        "VISIT https://a.in https://b.in https://c.in"
    )
    result = check_cold_email_spam("DEAL OF THE YEAR", shouting)
    assert result["caps_density"] > 0.15
    assert result["exclamation_density"] > 0.02
    assert result["link_density"] > 0.03
    assert any("capitals" in w for w in result["warnings"])
    assert any("exclamation" in w for w in result["warnings"])
    assert any("Link density" in w for w in result["warnings"])


def test_a_quiet_body_has_low_density():
    result = check_cold_email_spam(
        "A question",
        "Hi there. I had a look at your site and wanted to ask you something. "
        "Would you be open to a short call?",
    )
    assert result["caps_density"] == 0.0
    assert result["exclamation_density"] == 0.0
    assert result["link_density"] == 0.0


def test_the_finding_is_reported_once():
    """A phrase in two lists must not be counted twice."""
    result = check_cold_email_spam(
        "Business proposal",
        "Dear Sir/Madam,\n\nPlease revert back.\n\nRegards",
    )
    tells = result["india_tells"]
    assert len(tells) == len(set(tells))
    assert not (set(result["india_risk_phrases"]) & set(tells))
