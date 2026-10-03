import pytest
from app.campaigns.spam_checker import check_cold_email_spam

def test_spam_checker_clean_email():
    subject = "Quick question regarding {{business_name}}"
    body = (
        "Hi {{first_name}},\n\n"
        "Came across {{business_name}} while reviewing top specialists in {{city}}.\n"
        "Are you open to a brief chat this week about streamlining client acquisition?\n\n"
        "Best regards,\nAryan"
    )
    res = check_cold_email_spam(subject, body)
    assert res["score"] >= 85
    assert res["tier"] in ["Excellent", "Good"]
    assert res["is_safe"] is True
    assert len(res["high_risk_words"]) == 0

def test_spam_checker_high_risk_email():
    subject = "100% FREE GUARANTEED CASH NOW!!!!"
    body = (
        "Dear Friend,\n"
        "Claim your prize and make money with zero risk! Act now for pure profit!\n"
        "Click here: https://example.com/1 https://example.com/2 https://example.com/3 https://example.com/4"
    )
    res = check_cold_email_spam(subject, body)
    assert res["score"] <= 40
    assert res["tier"] == "High Spam Risk"
    assert res["is_safe"] is False
    assert len(res["high_risk_words"]) >= 3
    assert any("subject line" in w.lower() for w in res["warnings"])
