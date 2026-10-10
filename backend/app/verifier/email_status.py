"""
Normalized email verification taxonomy.

LeadForge collapses every provider's response into one stable enum so that
`Contact.verification_status` is comparable across SMTP, DNS and external
waterfall providers (ZeroBounce, NeverBounce, Bouncer, Hunter, Apollo...).

Two axes, exactly like the paid tools:

* ``status``     - coarse, safe to build campaign gating on.
* ``sub_status`` - granular, for explaining a result to a human.

Importantly, NOTHING in here maps an *unknown* outcome to VALID. The single
most common verification bug is treating "port 25 blocked" or "greylisted" as
a deliverable address, which quietly inflates bounce rates and burns the
sending domain's reputation.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

__all__ = [
    "EmailStatus",
    "VerificationResult",
    "ROLE_ACCOUNTS",
    "FREE_PROVIDERS",
    "DISPOSABLE_DOMAINS",
    "NO_PROBE_MX_PATTERNS",
    "PLACEHOLDER_DOMAINS",
    "detect_role_account",
    "detect_free_provider",
    "detect_disposable",
    "detect_placeholder_domain",
    "looks_like_gibberish",
    "did_you_mean_domain",
    "split_email",
    "classify_email",
    "should_send",
]


class EmailStatus(str, Enum):
    """Coarse verification status. Values are persisted to the DB."""

    VALID = "valid"
    INVALID = "invalid"
    CATCH_ALL = "catch_all"
    CATCH_ALL_UNKNOWN = "catch_all_unknown"
    DISPOSABLE = "disposable"
    ROLE_ACCOUNT = "role_account"
    FREE_EMAIL = "free_email"
    GREYLISTED = "greylisted"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    SYNTAX_ERROR = "syntax_error"
    DOMAIN_ERROR = "domain_error"
    NO_MX = "no_mx"
    SMTP_ERROR = "smtp_error"
    TIMEOUT = "timeout"
    SPAMTRAP = "spamtrap"
    ABUSE = "abuse"
    DO_NOT_MAIL = "do_not_mail"
    GIBBERISH = "gibberish"
    POSSIBLE_TYPO = "possible_typo"


# --- Data lists -------------------------------------------------------------
# Kept deliberately explicit rather than fetched over the network: a verifier
# must stay deterministic and offline-capable. Extend as needed.

ROLE_ACCOUNTS = frozenset(
    {
        "info", "contact", "sales", "support", "hello", "admin", "office",
        "enquiry", "enquiries", "inquiry", "inquiries", "help", "helpdesk",
        "marketing", "billing", "accounts", "reception", "receptionist",
        "team", "service", "services", "orders", "booking", "bookings",
        "appointments", "careers", "jobs", "hr", "press", "media", "legal",
        "privacy", "security", "abuse", "postmaster", "webmaster", "noreply",
        "no-reply", "donotreply", "mail", "email", "general", "enquire",
    }
)

#: Free / webmail providers. Common on Indian SMB leads - most sole traders use
#: a personal Gmail rather than a domain mailbox, so these are a *quality
#: signal* here, never a rejection reason.
FREE_PROVIDERS = frozenset(
    {
        "gmail.com", "googlemail.com",
        "yahoo.com", "yahoo.co.in", "yahoo.in", "ymail.com",
        "outlook.com", "hotmail.com", "live.com", "msn.com",
        "rediffmail.com", "rediff.com",
        "zohomail.in", "zohomail.com",
        "icloud.com", "me.com", "mac.com",
        "proton.me", "protonmail.com", "protonmail.ch",
        "aol.com", "gmx.com", "mail.com", "yandex.com",
        "in.com", "sify.com", "bsnl.in",
    }
)

DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
        "throwawaymail.com", "trashmail.com", "sharklasers.com", "yopmail.com",
        "getairmail.com", "dispostable.com", "maildrop.cc", "fakemailgenerator.com",
        "temp-mail.org", "tempr.email", "mailnesia.com", "mintemail.com",
        "spamgourmet.com", "mytemp.email", "discard.email", "fakeinbox.com",
        "mailcatch.com", "trash-mail.com", "getnada.com", "emailondeck.com",
    }
)

#: Hosts that only ever appear as boilerplate / CDN / framework noise in HTML.
#: NOTE: real corporate domains such as google.com must NOT live here - a
#: genuine employee@company address is not noise.
PLACEHOLDER_DOMAINS = frozenset(
    {
        "example.com", "example.org", "example.net", "test.com", "localhost",
        "domain.com", "email.com", "yourdomain.com", "mydomain.com",
        "sentry.io", "wixpress.com", "wix.com", "schema.org", "godaddy.com",
        "wordpress.com", "shopify.com", "squarespace.com", "w3.org",
    }
)

#: MX hostname fragments whose operators accept-all on RCPT TO: then reject
#: after DATA (or actively blocklist probing IPs). Probing them yields false
#: "valid" results and gets your egress IP penalised - so we never probe.
NO_PROBE_MX_PATTERNS = (
    "aspmx.l.google.com",
    "googlemail-smtp-in.l.google.com",
    "mx.zoho.com",
    "mx.zoho.in",
    "mx2.zoho.com",
    "mx2.zoho.in",
    "mail.protection.outlook.com",
    "am0.yahoodns.net",
    "rediffmailpro.com",
    "mx.sendgrid.net",
    "mx.mandrillapp.net",
)

#: Common typo'd domains -> canonical. Used for did_you_mean, not rejection.
_TYPO_MAP = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmail.co": "gmail.com",
    "gmail.con": "gmail.com",
    "gmail.cm": "gmail.com",
    "gnail.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "hotnail.com": "hotmail.com",
    "outlok.com": "outlook.com",
    "outloook.com": "outlook.com",
    "rediffmai.com": "rediffmail.com",
}

_SYNTAX_RE = re.compile(r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$")
_VOWELS = set("aeiou")
_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}")

# --- Result object ----------------------------------------------------------
class VerificationResult:
    """Immutable verification outcome. Never coerces unknown -> valid."""

    __slots__ = ("status", "sub_status", "confidence", "detail", "mx_host", "is_role", "is_free")

    def __init__(
        self,
        status: EmailStatus,
        sub_status: Optional[str] = None,
        confidence: float = 0.0,
        detail: Optional[str] = None,
        mx_host: Optional[str] = None,
        is_role: bool = False,
        is_free: bool = False,
    ) -> None:
        self.status = status if isinstance(status, EmailStatus) else EmailStatus(status)
        self.sub_status = sub_status or self.status.value
        self.confidence = float(confidence)
        self.detail = detail
        self.mx_host = mx_host
        self.is_role = is_role
        self.is_free = is_free

    @property
    def is_deliverable(self) -> bool:
        """Not known-bad. Broader than `sendable`."""
        return self.status in (
            EmailStatus.VALID, EmailStatus.ROLE_ACCOUNT, EmailStatus.FREE_EMAIL,
        )

    @property
    def sendable(self) -> bool:
        """Whether we should put this address on a cold campaign."""
        return self.status == EmailStatus.VALID

    def as_tuple(self) -> tuple:
        """Back-compat shim for the old `(bool, reason)` contract."""
        return self.is_deliverable, self.sub_status

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "sub_status": self.sub_status,
            "confidence": self.confidence,
            "detail": self.detail,
            "mx_host": self.mx_host,
            "is_role": self.is_role,
            "is_free": self.is_free,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<VerificationResult {self.sub_status} conf={self.confidence:.2f}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VerificationResult):
            return (self.status, self.sub_status, self.confidence) == (
                other.status, other.sub_status, other.confidence,
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.status, self.sub_status, self.confidence))


# --- Detectors --------------------------------------------------------------
def detect_role_account(local: Optional[str]) -> bool:
    """True if the local-part is a shared/group mailbox rather than a person.

    Role addresses are legitimate leads (on an SMB site they are often the
    *only* address), but they must never be counted as "person found".
    """
    if not local:
        return False
    local = local.strip().lower()
    if local in ROLE_ACCOUNTS:
        return True
    # info.acme@ / info-acme@ style variants
    stripped = re.split(r"[._+-]", local)[0]
    return stripped in ROLE_ACCOUNTS


def detect_free_provider(domain: Optional[str]) -> bool:
    return bool(domain) and domain.strip().lower() in FREE_PROVIDERS


def detect_disposable(domain: Optional[str]) -> bool:
    return bool(domain) and domain.strip().lower() in DISPOSABLE_DOMAINS


def detect_placeholder_domain(domain: Optional[str]) -> bool:
    """Noise hosts scraped out of HTML boilerplate (CDN/framework/example).

    Scope this to placeholders only - excluding real corporate domains like
    google.com throws away genuine leads.
    """
    if not domain:
        return False
    d = domain.strip().lower()
    return d in PLACEHOLDER_DOMAINS or d.endswith(".example") or d.endswith(".invalid")



def looks_like_gibberish(local: Optional[str]) -> bool:
    """Heuristic for bot-generated / hashed mailboxes (e.g. ``e65rc109q@``).

    Signals, chosen to avoid flagging real names:
    * an implausibly long consonant run, or
    * high digit density, or
    * long alternating consonant/vowel soup with no digits at all.
    """
    if not local:
        return False
    local = local.strip().lower()
    if len(local) < 8:
        return False
    if _CONSONANT_RUN.search(local):
        return True
    # Real personal mailboxes carry at most one or two digits ("john3", "ali2k").
    # Count digits per dot/underscore/hyphen separated token so that
    # "smita.sharma" is not judged on its length alone, and so that
    # "e65rc109q" trips on a single digit-heavy token.
    tokens = [t for t in re.split(r"[._+-]", local) if t]
    for token in tokens:
        digits = sum(c.isdigit() for c in token)
        if digits >= 3:
            return True
        if token and digits / len(token) >= 0.5 and len(token) >= 6:
            return True
    core = re.sub(r"[^a-z]", "", local)
    total_digits = sum(c.isdigit() for c in local)
    # Count vowel *positions*, not distinct vowel letters - {i,a} is 2 either way
    # but "smitasharma" has 4 vowel positions and must not trip this.
    vowel_count = sum(1 for c in core if c in _VOWELS)
    consonant_count = len(core) - vowel_count
    if len(core) >= 9 and not total_digits and consonant_count >= len(core) * 0.75:
        alternations = sum(1 for a, b in zip(core, core[1:]) if (a in _VOWELS) != (b in _VOWELS))
        if alternations >= 6:
            return True
    return False


def did_you_mean_domain(domain: Optional[str]) -> Optional[str]:
    """Returns the canonical domain for a known typo, else None."""
    if not domain:
        return None
    return _TYPO_MAP.get(domain.strip().lower())


def split_email(email: str) -> tuple:
    """Splits ``local@domain`` into lowercase parts. Either half may be ''."""
    local, _, domain = email.strip().lower().rpartition("@")
    return local, domain


def classify_email(email: str) -> VerificationResult:
    """Pre-SMTP classification: syntax, typo, gibberish, role, free, disposable.

    This is the cheap half of verification and is all an India-focused funnel
    needs for Gmail/Zoho/Outlook leads, because those MXes cannot be probed
    reliably anyway.
    """
    if not email or not isinstance(email, str) or not email.strip():
        return VerificationResult(EmailStatus.INVALID, "empty", 0.0, "no address supplied")

    clean = email.strip().lower()
    if not _SYNTAX_RE.match(clean) or ".." in clean or clean.startswith("."):
        return VerificationResult(EmailStatus.SYNTAX_ERROR, "invalid_syntax", 1.0, f"malformed: {clean}")

    local, domain = split_email(clean)
    if not local or not domain or "." not in domain:
        return VerificationResult(EmailStatus.SYNTAX_ERROR, "invalid_syntax", 1.0, f"malformed: {clean}")

    typo = did_you_mean_domain(domain)
    if typo:
        return VerificationResult(
            EmailStatus.POSSIBLE_TYPO, f"possible_typo:{typo}", 0.9,
            f"{domain} looks like {typo}", is_role=detect_role_account(local),
        )

    if looks_like_gibberish(local):
        return VerificationResult(EmailStatus.GIBBERISH, "gibberish", 0.85, f"local part looks generated: {local}")

    is_role = detect_role_account(local)
    is_free = detect_free_provider(domain)

    if detect_disposable(domain):
        return VerificationResult(
            EmailStatus.DISPOSABLE, "disposable_domain", 1.0, f"{domain} is disposable",
            is_role=is_role, is_free=is_free,
        )

    if detect_placeholder_domain(domain):
        return VerificationResult(
            EmailStatus.DOMAIN_ERROR, "placeholder_domain", 1.0, f"{domain} is HTML boilerplate",
            is_role=is_role,
        )

    # Passed the cheap checks. Final status is decided by the SMTP/DNS stage.
    return VerificationResult(EmailStatus.UNKNOWN, "precheck_passed", 0.3, None, is_role=is_role, is_free=is_free)


#: Statuses allowed onto a cold campaign. Deliberately includes ROLE_ACCOUNT
#: and FREE_EMAIL: for Indian SMBs an info@ address or a personal Gmail often
#: *is* the only business contact, so excluding them would empty the funnel.
#: They are tracked separately via `is_role`/`is_free` instead of being blocked.
_SENDABLE_STATUSES = frozenset({
    EmailStatus.VALID,
    EmailStatus.FREE_EMAIL,
    EmailStatus.ROLE_ACCOUNT,
})


def should_send(result: VerificationResult) -> bool:
    """Campaign send-gate.

    send           -> VALID, FREE_EMAIL, ROLE_ACCOUNT
    risky/segment  -> CATCH_ALL, CATCH_ALL_UNKNOWN  (send only if corroborated)
    never send     -> INVALID, DISPOSABLE, SPAMTRAP, ABUSE, DO_NOT_MAIL,
                      SYNTAX_ERROR, DOMAIN_ERROR, NO_MX, GIBBERISH, POSSIBLE_TYPO
    retry          -> GREYLISTED, BLOCKED, TIMEOUT, SMTP_ERROR, UNKNOWN
                      (do NOT count as valid, do NOT send yet)
    """
    return result.status in _SENDABLE_STATUSES

