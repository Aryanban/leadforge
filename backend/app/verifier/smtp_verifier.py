"""Email verification: MX resolution, SMTP handshake, multi-probe catch-all.

Design rules (these are the reason this module exists):

1. **Never coerce an unknown into a valid.** The previous implementation
   returned ``(True, "valid_mx")`` whenever port 25 was blocked or greylisted,
   which on cloud/Indian-ISP egress is the *common* case. That silently
   inflated valid counts and burned deliverability. Every failure path here
   returns a distinct non-valid status.
2. **Don't probe accept-all MXes.** Google/Zoho/Outlook/Yahoo answer ``250`` to
   every ``RCPT TO`` and then reject after DATA, or blocklist the probing IP.
   For those domains the cheap classification in ``email_status`` is the answer.
3. **Catch-all needs multiple probes.** A single random ``RCPT`` cannot separate
   catch-all from blocked / greylisted / anti-spam-gateway.
"""

import asyncio
import dns.exception
import dns.resolver
import logging
import smtplib
import socket
import time
from typing import Dict, List, Optional, Tuple

from app.verifier.email_status import (
    DISPOSABLE_DOMAINS,
    EmailStatus,
    NO_PROBE_MX_PATTERNS,
    VerificationResult,
    classify_email,
    detect_free_provider,
    detect_role_account,
)

logger = logging.getLogger(__name__)

EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

#: SMTP codes that mean "try again later" - never "valid".
_GREYLIST_CODES = (450, 451, 452, 453, 421)
#: Codes that mean the server is refusing *us*, not judging the mailbox.
_BLOCKED_CODES = (554, 571, 572, 573, 574, 575)
#: Codes that definitively mean "no such mailbox".
_INVALID_CODES = (550, 551, 553, 500, 501, 502, 504)

DNS_TIMEOUT = 3.0
SMTP_TIMEOUT = 8.0
#: Seconds to wait before the greylist retry attempt.
GREYLIST_RETRY_DELAY = 60.0

#: Retained for backwards compatibility with existing imports/tests.
DISPOSABLE_LEGACY = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "throwawaymail.com", "trashmail.com", "sharklasers.com", "yopmail.com",
    "getairmail.com", "dispostable.com", "maildrop.cc", "fakemailgenerator.com",
}


def _decode(raw) -> str:
    if isinstance(raw, bytes):
        return raw.decode('utf-8', 'replace').strip()
    return str(raw).strip()


def get_mx_records(domain: str) -> List[Tuple[int, str]]:
    """Returns ``[(preference, exchange), ...]`` sorted by preference.

    Sorting matters: ``records[0]`` from dnspython is not guaranteed to be the
    primary MX, and trying a backup MX first gives misleading answers.
    Falls back to the A record when no MX exists, per RFC 5321 5.1.
    """
    resolver = dns.resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT
    resolver.lifetime = DNS_TIMEOUT

    try:
        answers = resolver.resolve(domain, 'MX')
        records = sorted(
            ((int(r.preference), str(r.exchange).rstrip('.')) for r in answers),
            key=lambda pair: pair[0],
        )
        if records:
            return records
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        raise
    except dns.exception.DNSException as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)

    # No MX records: implicit MX (A record) per RFC 5321 5.1.
    try:
        answers = resolver.resolve(domain, 'A')
        ips = [str(r) for r in answers]
        if ips:
            return [(0, ips[0])]
    except dns.exception.DNSException as exc:
        logger.debug("A-record fallback failed for %s: %s", domain, exc)
    return []


def mx_is_no_probe(mx_host: Optional[str]) -> bool:
    """True if this MX accepts everything on RCPT and punishes probing."""
    if not mx_host:
        return False
    host = mx_host.lower()
    return any(pattern in host for pattern in NO_PROBE_MX_PATTERNS)


def _classify_rcpt_code(code: Optional[int]) -> EmailStatus:
    if code is None:
        return EmailStatus.UNKNOWN
    if code in (250, 251):
        return EmailStatus.VALID
    if code == 252:
        # "Cannot verify but will attempt" - an accept-all hint, not a valid.
        return EmailStatus.CATCH_ALL_UNKNOWN
    if code in _GREYLIST_CODES:
        return EmailStatus.GREYLISTED
    if code in _BLOCKED_CODES:
        return EmailStatus.BLOCKED
    if code in _INVALID_CODES:
        return EmailStatus.INVALID
    return EmailStatus.UNKNOWN


class _SMTPProbe:
    """SMTP prober that keeps one connection alive across several RCPT commands.

    Opening a connection per candidate is what gets an egress IP rate limited.
    """

    def __init__(self, mx_host: str, sender_email: str) -> None:
        self.mx_host = mx_host
        self.sender_email = sender_email
        self.server: Optional[smtplib.SMTP] = None
        self.error: Optional[str] = None

    def connect(self) -> bool:
        try:
            self.server = smtplib.SMTP(self.mx_host, port=25, timeout=SMTP_TIMEOUT)
            self.server.set_debuglevel(0)
            self.server.ehlo_or_helo_if_needed()
            self.server.mail(self.sender_email)
            return True
        except (socket.timeout, OSError, smtplib.SMTPConnectError,
                smtplib.SMTPServerDisconnected, smtplib.SMTPException) as exc:
            self.error = f"connect_failed:{type(exc).__name__}"
            return False

    def rcpt(self, address: str) -> Tuple[Optional[int], str]:
        """Returns ``(code, message)``. Code is None on transport failure."""
        if self.server is None:
            return None, self.error or "not_connected"
        try:
            code, raw = self.server.rcpt(address)
            return code, _decode(raw)
        except smtplib.SMTPServerDisconnected as exc:
            self.server = None
            return None, f"disconnected:{exc}"
        except (socket.timeout, OSError, smtplib.SMTPException) as exc:
            self.server = None
            return None, f"rcpt_failed:{type(exc).__name__}"

    def close(self) -> None:
        if self.server is not None:
            for closer in ("quit", "close"):
                try:
                    getattr(self.server, closer)()
                    break
                except Exception:
                    continue
            self.server = None



def verify_email(email: str, sender_email: str = "verify@leadforge.dev",
                 catch_all_ok: bool = True) -> VerificationResult:
    """Full verification returning a :class:`VerificationResult`.

    Order of operations is deliberately cheap-first: syntax/typo/gibberish/
    role/free/disposable classification, then DNS, then SMTP.
    """
    precheck = classify_email(email)
    if precheck.status is not EmailStatus.UNKNOWN:
        return precheck

    is_role = precheck.is_role
    is_free = precheck.is_free or detect_free_provider(
        email.strip().lower().rpartition("@")[2]
    )
    local_part, _, domain = email.strip().lower().rpartition("@")

    try:
        mx_records = get_mx_records(domain)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return VerificationResult(EmailStatus.INVALID, "invalid_domain", 1.0,
                                  f"{domain} does not resolve")
    except Exception as exc:
        return VerificationResult(EmailStatus.DOMAIN_ERROR, "unresolvable_domain", 0.5,
                                  f"DNS error for {domain}: {exc}")

    if not mx_records:
        return VerificationResult(EmailStatus.NO_MX, "no_mx_records", 0.9,
                                  f"no MX or A record for {domain}")

    mx_host = mx_records[0][1]

    # Accept-all MXes: probing produces a false VALID and risks a blocklist.
    if mx_is_no_probe(mx_host):
        if is_free:
            return VerificationResult(
                EmailStatus.FREE_EMAIL, "free_email_unprobed", 0.6,
                f"{mx_host} accepts-all on RCPT; classified from address only",
                mx_host=mx_host, is_role=is_role, is_free=True,
            )
        return VerificationResult(
            EmailStatus.CATCH_ALL_UNKNOWN, "accept_all_mx_unprobed", 0.4,
            f"{mx_host} accepts-all on RCPT; not probed (would report a false valid)",
            mx_host=mx_host, is_role=is_role, is_free=is_free,
        )

    probe = _SMTPProbe(mx_host, sender_email)
    if not probe.connect():
        return VerificationResult(
            EmailStatus.UNKNOWN, probe.error or "smtp_unreachable", 0.0,
            f"could not connect to {mx_host}:25 - enqueue for retry, do NOT treat as valid",
            mx_host=mx_host, is_role=is_role, is_free=is_free,
        )

    try:
        code, message = probe.rcpt(email.strip().lower())
        status = _classify_rcpt_code(code)

        # A VALID from an unknown MX may still be an accept-all. Confirm with
        # the catch-all control before we let it through as sendable.
        if status is EmailStatus.VALID:
            verdict = probe_catch_all(domain, probe=probe, sender_email=sender_email)
            if verdict == "catch_all":
                return VerificationResult(
                    EmailStatus.CATCH_ALL if catch_all_ok else EmailStatus.CATCH_ALL_UNKNOWN,
                    "catch_all", 0.5,
                    "domain accepts random RCPT; mailbox unconfirmed",
                    mx_host=mx_host, is_role=is_role, is_free=is_free,
                )

        confidence = {
            EmailStatus.VALID: 0.95,
            EmailStatus.INVALID: 0.95,
            EmailStatus.CATCH_ALL: 0.5,
            EmailStatus.GREYLISTED: 0.0,
            EmailStatus.BLOCKED: 0.0,
        }.get(status, 0.1)
        detail = f"rcpt {code}: {message}" if code is not None else message
        return VerificationResult(status, status.value, confidence, detail,
                                  mx_host=mx_host, is_role=is_role, is_free=is_free)
    finally:
        probe.close()




def probe_catch_all(domain: str, probe: Optional[_SMTPProbe] = None,
                    sender_email: str = "verify@leadforge.dev") -> str:
    """Multi-probe catch-all detection.

    Returns one of:
      ``catch_all``        - random probe AND known-invalid probe both accepted
      ``not_catch_all``    - known-invalid probe rejected, so RCPT is meaningful
      ``blocked``          - server refused every RCPT (rate limit / policy)
      ``greylisted_retry`` - transient 4xx; retry later
      ``unknown``          - could not determine
    """
    if not domain:
        return "unknown"
    domain = domain.strip().lower()
    if domain in DISPOSABLE_DOMAINS:
        return "unknown"

    owned_probe = None
    if probe is None:
        try:
            mx_records = get_mx_records(domain)
        except Exception:
            return "unknown"
        if not mx_records:
            return "unknown"
        mx_host = mx_records[0][1]
        if mx_is_no_probe(mx_host):
            return "blocked"
        owned_probe = probe = _SMTPProbe(mx_host, sender_email)
        if not probe.connect():
            return "blocked"

    try:
        stamp = int(time.time())
        code_r, _ = probe.rcpt(f"leadforge-probe-{stamp}@{domain}")

        if code_r is None or code_r in _GREYLIST_CODES:
            return "greylisted_retry"
        if code_r in _BLOCKED_CODES:
            return "blocked"

        # Control probe: a known-invalid shape on the same server.
        code_i, _ = probe.rcpt(f"leadforge-no-such-mailbox-{stamp}@{domain}")

        if code_r == 250 and code_i == 250:
            return "catch_all"
        if code_r in _INVALID_CODES or code_i in _INVALID_CODES:
            return "not_catch_all"
        if code_i in _BLOCKED_CODES:
            return "blocked"
        return "unknown"
    finally:
        if owned_probe is not None:
            owned_probe.close()


def verify_email_smtp(email: str, sender_email: str = "verify@leadforge.dev") -> Tuple[bool, str]:
    """Backwards-compatible ``(bool, reason)`` shim.

    Kept because ``email_finder``, ``workers/tasks`` and the existing tests use
    the tuple form. The bool means *deliverable* (not known-bad), which is the
    conservative reading. Callers that need send-gating should use
    :func:`~app.verifier.email_status.should_send` on :func:`verify_email`.
    """
    return verify_email(email, sender_email=sender_email).as_tuple()


def check_catch_all_domain(domain: str) -> bool:
    """Backwards-compatible catch-all check used by ``email_finder``."""
    return probe_catch_all(domain) == "catch_all"


# --- Async / batch layer ----------------------------------------------------
# The functions above are deliberately synchronous: smtplib and dnspython are
# blocking, and keeping them sync makes them trivial to unit test. But
# ``enrich_business_by_id`` is an ``async def``, so calling them directly
# stalls the whole event loop for the 3-8s of a DNS+SMTP round trip and makes
# the API unresponsive for the duration of an enrichment run. Everything below
# moves that work off the loop and reuses work across addresses.

#: Concurrent SMTP sessions. Port-25 egress gets an IP blocklisted quickly, so
#: this is intentionally modest - paid verifiers spread load across many
#: datacentre IPs, which we cannot do, so we stay polite instead.
VERIFY_CONCURRENCY = 8

_verify_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_lock: Optional[asyncio.Lock] = None


async def _get_semaphore() -> asyncio.Semaphore:
    """Lazily creates the semaphore inside the running loop.

    A module-level ``asyncio.Semaphore()`` binds to the first loop that touches
    it and then raises ``bound to a different event loop`` under any second
    loop (every test creates a fresh one), so it must be created per-loop.
    """
    global _verify_semaphore, _semaphore_lock
    if _semaphore_lock is None:
        _semaphore_lock = asyncio.Lock()
    if _verify_semaphore is None:
        async with _semaphore_lock:
            if _verify_semaphore is None:
                _verify_semaphore = asyncio.Semaphore(VERIFY_CONCURRENCY)
    return _verify_semaphore


async def verify_email_async(email: str, sender_email: str = "verify@leadforge.dev",
                             catch_all_ok: bool = True) -> VerificationResult:
    """Non-blocking :func:`verify_email`. Use this from ``async def`` code."""
    semaphore = await _get_semaphore()
    async with semaphore:
        return await asyncio.to_thread(verify_email, email, sender_email, catch_all_ok)


async def probe_catch_all_async(domain: str,
                                sender_email: str = "verify@leadforge.dev") -> str:
    """Non-blocking :func:`probe_catch_all`."""
    return await asyncio.to_thread(probe_catch_all, domain, None, sender_email)


async def check_catch_all_domain_async(domain: str) -> bool:
    """Non-blocking :func:`check_catch_all_domain`."""
    return await asyncio.to_thread(check_catch_all_domain, domain)

def _verify_one_domain_sync(domain: str, emails: List[str], sender_email: str,
                            catch_all_ok: bool) -> List[Tuple[str, VerificationResult]]:
    """Verifies every address on one domain over a single MX probe.

    This is the throughput win: N candidates on ``acme.in`` cost one DNS
    lookup and one TCP connection instead of N of each. Reopening a connection
    per candidate is exactly what gets an egress IP throttled, and the
    catch-all verdict is decided once for the domain rather than per address.
    """
    if not emails:
        return []

    # Cheap classification first - needs no network at all.
    results: List[Tuple[str, VerificationResult]] = []
    needs_smtp: List[str] = []
    for email in emails:
        precheck = classify_email(email)
        if precheck.status is not EmailStatus.UNKNOWN:
            results.append((email, precheck))
        else:
            needs_smtp.append(email)

    if not needs_smtp:
        return results

    try:
        mx_records = get_mx_records(domain)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return results + [
            (e, VerificationResult(EmailStatus.INVALID, "invalid_domain", 1.0,
                                   f"{domain} does not resolve")) for e in needs_smtp
        ]
    except Exception as exc:
        return results + [
            (e, VerificationResult(EmailStatus.DOMAIN_ERROR, "unresolvable_domain", 0.5,
                                   f"DNS error for {domain}: {exc}")) for e in needs_smtp
        ]

    if not mx_records:
        return results + [
            (e, VerificationResult(EmailStatus.NO_MX, "no_mx_records", 0.9,
                                   f"no MX or A record for {domain}")) for e in needs_smtp
        ]

    mx_host = mx_records[0][1]

    # Accept-all MXes: one verdict covers the whole domain, and probing them
    # would manufacture false valids, so we classify from the address only.
    if mx_is_no_probe(mx_host):
        for email in needs_smtp:
            is_free = detect_free_provider(domain)
            is_role = detect_role_account(email.rpartition("@")[0])
            if is_free:
                results.append((email, VerificationResult(
                    EmailStatus.FREE_EMAIL, "free_email_unprobed", 0.6,
                    f"{mx_host} accepts-all on RCPT; classified from address only",
                    mx_host=mx_host, is_role=is_role, is_free=True)))
            else:
                results.append((email, VerificationResult(
                    EmailStatus.CATCH_ALL_UNKNOWN, "accept_all_mx_unprobed", 0.4,
                    f"{mx_host} accepts-all on RCPT; not probed (would report a false valid)",
                    mx_host=mx_host, is_role=is_role, is_free=is_free)))
        return results

    probe = _SMTPProbe(mx_host, sender_email)
    if not probe.connect():
        for email in needs_smtp:
            results.append((email, VerificationResult(
                EmailStatus.UNKNOWN, probe.error or "smtp_unreachable", 0.0,
                f"could not connect to {mx_host}:25 - enqueue for retry, do NOT treat as valid",
                mx_host=mx_host, is_role=detect_role_account(email.rpartition("@")[0]),
                is_free=detect_free_provider(domain))))
        return results

    try:
        verdict = "not_catch_all"
        if catch_all_ok:
            try:
                verdict = probe_catch_all(domain, probe=probe, sender_email=sender_email)
            except Exception:
                verdict = "unknown"

        for email in needs_smtp:
            is_role = detect_role_account(email.rpartition("@")[0])
            is_free = detect_free_provider(domain)

            if probe.server is None:
                results.append((email, VerificationResult(
                    EmailStatus.UNKNOWN, "smtp_unreachable", 0.0,
                    "SMTP session dropped; re-enqueue for retry",
                    mx_host=mx_host, is_role=is_role, is_free=is_free)))
                continue

            code, message = probe.rcpt(email)
            status = _classify_rcpt_code(code)

            if status is EmailStatus.VALID and verdict == "catch_all":
                status = EmailStatus.CATCH_ALL if catch_all_ok else EmailStatus.CATCH_ALL_UNKNOWN
                message = "domain accepts random RCPT; mailbox unconfirmed"

            confidence = {
                EmailStatus.VALID: 0.95,
                EmailStatus.INVALID: 0.95,
                EmailStatus.CATCH_ALL: 0.5,
                EmailStatus.GREYLISTED: 0.0,
                EmailStatus.BLOCKED: 0.0,
            }.get(status, 0.1)
            detail = f"rcpt {code}: {message}" if code is not None else message
            results.append((email, VerificationResult(
                status, status.value, confidence, detail,
                mx_host=mx_host, is_role=is_role, is_free=is_free)))
        return results
    finally:
        probe.close()


async def verify_batch(emails: List[str], sender_email: str = "verify@leadforge.dev",
                       catch_all_ok: bool = True) -> Dict[str, VerificationResult]:
    """Verifies many addresses, grouping so each domain is probed exactly once.

    Runs off the event loop with bounded concurrency: one DNS lookup and one
    SMTP connection per *distinct domain* rather than per address. Returns
    ``{email: VerificationResult}`` and never raises for a single bad domain.
    """
    cleaned = [e.strip().lower() for e in emails if e and e.strip()]
    if not cleaned:
        return {}

    by_domain: Dict[str, List[str]] = {}
    for email in dict.fromkeys(cleaned):  # de-dupe, preserve order
        by_domain.setdefault(email.rpartition("@")[2], []).append(email)

    semaphore = await _get_semaphore()
    loop = asyncio.get_running_loop()

    async def _run(domain: str, addrs: List[str]):
        async with semaphore:
            return await loop.run_in_executor(
                None, _verify_one_domain_sync, domain, addrs, sender_email, catch_all_ok,
            )

    gathered = await asyncio.gather(
        *(_run(domain, addrs) for domain, addrs in by_domain.items()),
        return_exceptions=True,
    )

    out: Dict[str, VerificationResult] = {}
    for outcome in gathered:
        if isinstance(outcome, BaseException):
            logger.warning("batch verification group failed: %s", outcome)
            continue
        for email, result in outcome:
            out[email] = result
    return out

