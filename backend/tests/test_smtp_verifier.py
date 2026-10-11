import pytest
from app.verifier.smtp_verifier import (
    verify_email, verify_email_smtp, mx_is_no_probe, DISPOSABLE_DOMAINS,
)
from app.verifier.email_status import EmailStatus, should_send


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


def test_gmail_mx_is_no_probe():
    """Regression: gmail-smtp-in.l.google.com must never be probed.

    Probing Gmail's accept-all MX manufactures false 'valid' verdicts and
    gets the egress IP penalised.
    """
    assert mx_is_no_probe("gmail-smtp-in.l.google.com")
    assert mx_is_no_probe("alt1.gmail-smtp-in.l.google.com")
    assert mx_is_no_probe("ALT2.GMAIL-SMTP-IN.L.GOOGLE.COM")
    assert mx_is_no_probe("aspmx.l.google.com")
    assert not mx_is_no_probe("mail.acme.in")
    assert not mx_is_no_probe(None)


def test_gmail_address_never_reports_valid(monkeypatch):
    """Even if port 25 were reachable, Gmail must classify, not probe."""
    import app.verifier.smtp_verifier as sv

    monkeypatch.setattr(
        sv, "get_mx_records",
        lambda domain: [(5, "gmail-smtp-in.l.google.com")],
    )
    # If the code probes anyway, this blows up the test.
    def _boom(*a, **k):
        raise AssertionError("must not open SMTP to an accept-all MX")
    monkeypatch.setattr(sv, "_SMTPProbe", _boom)

    result = verify_email("r.k.sharma@gmail.com")
    assert result.status == EmailStatus.FREE_EMAIL
    assert result.is_free is True
    # Gmail is the dominant SMB address in India: it must classify as
    # FREE_EMAIL (never VALID), never be probed, and stay out of the strict
    # send gate while remaining reachable via the India-aware gate.
    assert result.sendable is False
    assert should_send(result) is True


def test_connect_failure_is_unknown_never_valid(monkeypatch):
    """Blocked port 25 (cloud/ISP egress) must be UNKNOWN, never valid."""
    import app.verifier.smtp_verifier as sv

    monkeypatch.setattr(sv, "get_mx_records", lambda domain: [(10, "mail.acme.in")])

    class DeadProbe:
        def __init__(self, *a, **k):
            self.server = None
            self.error = "connect_failed:timeout"
        def connect(self):
            return False
        def close(self):
            pass

    monkeypatch.setattr(sv, "_SMTPProbe", DeadProbe)

    result = verify_email("someone@acme.in")
    assert result.status == EmailStatus.UNKNOWN
    assert should_send(result) is False
    assert result.as_tuple() == (False, "connect_failed:timeout")
