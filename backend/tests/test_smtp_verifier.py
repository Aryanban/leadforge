import pytest
from app.verifier.smtp_verifier import verify_email_smtp, DISPOSABLE_DOMAINS

def test_verify_email_invalid_syntax():
    valid, reason = verify_email_smtp("not-an-email")
    assert valid is False
    assert reason == "invalid_syntax"

def test_verify_email_empty():
    valid, reason = verify_email_smtp("")
    assert valid is False
    assert reason == "empty"

def test_verify_email_disposable_domain():
    valid, reason = verify_email_smtp("test@mailinator.com")
    assert valid is False
    assert reason == "disposable_domain"
