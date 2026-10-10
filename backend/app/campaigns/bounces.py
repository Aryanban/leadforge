"""SMTP bounce classification.

A boolean ``bounced`` flag cannot express the one distinction that matters
operationally: a permanent 5xx means the mailbox will never exist and the
address must be suppressed forever, while a 4xx or a gateway block is
transient and must be retried. Treating a transient failure as permanent burns
good leads; treating a permanent failure as transient gets you blocklisted.

Return values are the reason strings used by ``campaigns.suppression``, or
``None`` when the failure is not a bounce at all.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

HARD = "hard_bounce"
SOFT = "soft_bounce"

#: Extended status codes and free-text phrases that mean "permanently dead".
#: RFC 3463: class 5 (5.x.x) is permanent, class 4 (4.x.x) is transient.
_HARD_PATTERNS = (
    r"\b550\b", r"\b551\b", r"\b553\b", r"\b554\b",
    r"\b5\.1\.1\b", r"\b5\.1\.2\b", r"\b5\.1\.3\b", r"\b5\.1\.6\b",
    r"\b5\.1\.10\b", r"\b5\.2\.1\b", r"\b5\.4\.1\b", r"\b5\.7\.1\b",
    r"user unknown", r"no such user", r"does not exist", r"unknown recipient",
    r"mailbox unavailable", r"recipient rejected", r"address rejected",
    r"invalid recipient", r"no mailbox", r"account disabled", r"user not found",
    r"relay(?:ing)? denied", r"unrouteable address", r"deactivated",
)

#: Transient. Retry, and only suppress once the retry budget is exhausted.
_SOFT_PATTERNS = (
    r"\b450\b", r"\b451\b", r"\b452\b", r"\b421\b",
    r"\b4\.1\.\d\b", r"\b4\.2\.\d\b", r"\b4\.3\.\d\b", r"\b4\.4\.\d\b",
    r"\b4\.7\.\d\b",
    r"greylist", r"try again later", r"temporarily (?:deferred|unavailable)",
    r"service unavailable", r"connection (?:timed out|closed by remote host)",
    r"too many connections", r"rate limit", r"quota exceeded",
    r"mailbox full", r"over quota", r"insufficient system storage",
)

#: Policy rejections at connect/MAIL FROM time. NOT a property of the lead -
# retrying the same mailbox will not help, but the address is still valid.
_POLICY_PATTERNS = (
    r"\b5\.7\.1\b", r"blocked", r"blacklist", r"blocklist", r"spamhaus",
    r"barracuda", r"spam cop", r"rejected by policy", r"message rejected",
    r"content rejected", r"policy violation", r"poor reputation",
    r"ip not allowed", r"access denied", r"client host .* blocked",
)

_HARD_RE = re.compile("|".join(_HARD_PATTERNS), re.IGNORECASE)
_SOFT_RE = re.compile("|".join(_SOFT_PATTERNS), re.IGNORECASE)
_POLICY_RE = re.compile("|".join(_POLICY_PATTERNS), re.IGNORECASE)

#: RFC 3463 enhanced codes that specifically describe a *dead recipient*, as
#: opposed to a generic transaction failure. A 5xx carrying one of these is
#: permanently undeliverable no matter what the prose says.
_RECIPIENT_CODES = re.compile(
    r"5\.1\.1|5\.1\.2|5\.1\.3|5\.1\.6|5\.1\.10|5\.2\.1|5\.2\.2|5\.4\.1",
)

#: Bare SMTP reply code at the end of the message, e.g. "(550 5.1.1 ...)"
_CODE_RE = re.compile(r"\b([45]\d{2})\b")


def classify_bounce(error: Optional[str]) -> Optional[str]:
    """Maps an SMTP error string to ``hard_bounce`` / ``soft_bounce`` / None.

    ``None`` means "not a recipient problem" - a policy block or an unknown
    failure, which should be retried and must never suppress the lead.
    """
    if not error:
        return None

    text = error.strip().lower()
    if not text:
        return None

    # An explicit 4xx always wins over free-text matching, because the numeric
    # class is authoritative under RFC 3463 and many gateways wrap a 4xx in
    # prose containing the word "rejected".
    code_match = _CODE_RE.search(text)
    if code_match:
        code = int(code_match.group(1))
        if 400 <= code < 500:
            return SOFT
        if 500 <= code < 510:
            return _classify_5xx(text)

    # No numeric code. Fall back to phrase matching, most specific first.
    if _HARD_RE.search(text):
        return HARD
    if _SOFT_RE.search(text):
        return SOFT
    if _POLICY_RE.search(text):
        return None

    logger.debug("unclassifiable SMTP error, treating as soft: %s", text[:120])
    return SOFT


def _classify_5xx(text: str) -> Optional[str]:
    """Decides what a 5xx reply means.

    The numeric class alone is not enough. ``554 5.7.1 message rejected`` is a
    statement about *our* sender reputation, not about the recipient - if we
    suppressed on it we would delete valid leads and never learn we have a
    deliverability problem. So a 5xx is treated as a dead recipient only when
    it carries a recipient-specific enhanced code or says so in prose.
    """
    if _RECIPIENT_CODES.search(text):
        return HARD
    if _POLICY_RE.search(text):
        return None
    if _HARD_RE.search(text):
        return HARD
    if _SOFT_RE.search(text):
        return SOFT
    # Bare 550/551/553 with no detail: overwhelmingly a missing mailbox.
    if re.search(r"\b(?:550|551|553)\b", text):
        return HARD
    # A bare 554/5.x.x with nothing to go on is ambiguous - retry rather than
    # destroy the lead.
    return None


def should_retry(error: Optional[str]) -> bool:
    """Whether a failed send is worth retrying at all."""
    return classify_bounce(error) != HARD


def extract_smtp_code(error: Optional[str]) -> Optional[int]:
    """The first SMTP reply code in the message, if any."""
    if not error:
        return None
    match = _CODE_RE.search(error)
    return int(match.group(1)) if match else None
