"""India deliverability advisor — pure checks, no enforcement.

Self-hosted rule: the operator decides, the tool only informs. Every
function here returns *advice* (a dict with ``ok``/``warnings``). Nothing
gates, blocks, pauses, or rewrites a send. The dashboard renders these as
banners and checklists; ``execute_campaign_step`` never imports this module.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

#: DNS cache so repeated checks within one process do not hammer resolvers.
_auth_cache: Dict[str, dict] = {}

IST = "Asia/Kolkata"

#: TRAI quiet hours for promotional voice/SMS (IST, 24h clock, end-exclusive).
QUIET_START_HOUR = 21
QUIET_END_HOUR = 9


def _dns_txt(name: str) -> List[str]:
    """All TXT records at ``name``; empty list on any failure (NXDOMAIN etc)."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(name, "TXT", lifetime=3.0)
        out: List[str] = []
        for r in answers:
            try:
                out.append(b"".join(r.strings).decode("utf-8", "replace"))
            except Exception:
                out.append(str(r))
        return out
    except Exception:
        return []


def check_sender_auth(domain: str, use_cache: bool = True) -> Dict[str, Any]:
    """Advisory SPF/DKIM/DMARC check for a sending domain.

    Returns ``{"domain", "spf_ok", "dkim_ok", "dmarc_ok", "warnings"}``.
    ``dkim_ok`` probes common selectors — a miss only means "not found
    under a known selector", which the warning says plainly.
    """
    domain = (domain or "").strip().lower().lstrip("@")
    if use_cache and domain in _auth_cache:
        return dict(_auth_cache[domain])
    warnings: List[str] = []

    spf_ok = any(t.strip().lower().startswith("v=spf1") for t in _dns_txt(domain))
    if not spf_ok:
        warnings.append(
            f"{domain} publishes no SPF record — Gmail/Yahoo bulk-reject "
            "unauthenticated mail since Feb 2024. Add a TXT `v=spf1` record."
        )

    dkim_ok = False
    for selector in ("google", "default", "k1", "k2", "mail", "email",
                     "dkim", "s1", "s2", "zoho", "cm"):
        if _dns_txt(f"{selector}._domainkey.{domain}"):
            dkim_ok = True
            break
    if not dkim_ok:
        warnings.append(
            f"No DKIM key found under common selectors for {domain} — "
            "signing proves the mail wasn't tampered with in transit."
        )

    dmarc_txt = _dns_txt(f"_dmarc.{domain}")
    dmarc_ok = any(t.strip().lower().startswith("v=dmarc1") for t in dmarc_txt)
    if not dmarc_ok:
        warnings.append(
            f"{domain} publishes no DMARC policy — add "
            "`v=DMARC1; p=none; rua=mailto:you@domain` to get reports."
        )

    result = {
        "domain": domain, "spf_ok": spf_ok, "dkim_ok": dkim_ok,
        "dmarc_ok": dmarc_ok, "ok": spf_ok and dkim_ok and dmarc_ok,
        "warnings": warnings,
    }
    _auth_cache[domain] = dict(result)
    return result


async def check_sender_auth_async(domain: str, use_cache: bool = True) -> Dict[str, Any]:
    """Async advisory SPF/DKIM/DMARC check for a sending domain.

    The synchronous :func:`check_sender_auth` performs up to **13 blocking
    DNS TXT lookups**, each with a 3-second timeout. Called from an ``async
    def`` route that froze the event loop for up to ~39 seconds - and it was
    on the critical path of a page load, so a single request could stall the
    whole API for other users.

    Here every lookup runs in a worker thread and the DKIM selector probes
    run concurrently, so the wall clock is one timeout instead of thirteen.
    """
    domain = (domain or "").strip().lower().lstrip("@")
    if use_cache and domain in _auth_cache:
        return dict(_auth_cache[domain])

    selectors = ("google", "default", "k1", "k2", "mail", "email",
                 "dkim", "s1", "s2", "zoho", "cm")

    # Every DNS query at once, each off the event loop.
    results = await asyncio.gather(
        _dns_txt_async(domain),                       # SPF
        *[_dns_txt_async(f"{s}._domainkey.{domain}") for s in selectors],
        _dns_txt_async(f"_dmarc.{domain}"),           # DMARC
        return_exceptions=True,
    )

    spf_txt = _unwrap(results[0])
    dkim_hits = [_unwrap(r) for r in results[1:1 + len(selectors)]]
    dmarc_txt = _unwrap(results[-1])

    warnings: List[str] = []

    spf_ok = any(t.strip().lower().startswith("v=spf1") for t in spf_txt)
    if not spf_ok:
        warnings.append(
            f"{domain} publishes no SPF record — Gmail/Yahoo bulk-reject "
            "unauthenticated mail since Feb 2024. Add a TXT `v=spf1` record."
        )

    dkim_ok = any(dkim_hits)
    if not dkim_ok:
        warnings.append(
            f"No DKIM key found under common selectors for {domain} — "
            "signing proves the mail wasn't tampered with in transit."
        )

    dmarc_ok = any(t.strip().lower().startswith("v=dmarc1") for t in dmarc_txt)
    if not dmarc_ok:
        warnings.append(
            f"{domain} publishes no DMARC policy — add "
            "`v=DMARC1; p=none; rua=mailto:you@domain` to get reports."
        )

    result = {
        "domain": domain, "spf_ok": spf_ok, "dkim_ok": dkim_ok,
        "dmarc_ok": dmarc_ok, "ok": spf_ok and dkim_ok and dmarc_ok,
        "warnings": warnings,
    }
    _auth_cache[domain] = dict(result)
    return result


async def _dns_txt_async(name: str) -> List[str]:
    """A DNS TXT lookup that does not block the event loop."""
    return await asyncio.to_thread(_dns_txt, name)


def _unwrap(value: Any) -> Any:
    """``asyncio.gather(..., return_exceptions=True)`` helper."""
    if isinstance(value, BaseException):
        return []
    return value


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    """True when it is currently TRAI quiet hours (21:00–09:00 IST)."""
    now = now or datetime.now(timezone.utc)
    try:
        ist = now.astimezone(ZoneInfo(IST))
    except Exception:
        ist = now
    hour = ist.hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


#: The hours an Indian business actually answers email. TRAI's quiet hours
#: are about promotional voice and SMS; the reason not to send *email* at
#: 03:00 IST is simpler: the recipient is asleep, and an email that lands
#: at 03:00 is marked as spam by a human rather than a filter.
#:
#: A send outside this window is *deferred*, never dropped - the scheduler
#: picks it up on its next tick, which is inside the window.
EMAIL_SEND_START_HOUR = 9
EMAIL_SEND_END_HOUR = 20


def in_email_send_window(now: Optional[datetime] = None) -> bool:
    """Whether it is a reasonable hour to send an email in India."""
    now = now or datetime.now(timezone.utc)
    try:
        ist = now.astimezone(ZoneInfo(IST))
    except Exception:
        ist = now
    return EMAIL_SEND_START_HOUR <= ist.hour < EMAIL_SEND_END_HOUR


def next_send_window_opens(now: Optional[datetime] = None) -> Optional[str]:
    """A human-readable time for when the next send window opens."""
    now = now or datetime.now(timezone.utc)
    try:
        ist = now.astimezone(ZoneInfo(IST))
    except Exception:
        ist = now
    if ist.hour < EMAIL_SEND_START_HOUR:
        return f"{EMAIL_SEND_START_HOUR:02d}:00 IST"
    if ist.hour >= EMAIL_SEND_END_HOUR:
        return f"{EMAIL_SEND_START_HOUR:02d}:00 IST tomorrow"
    return None


def dlt_checklist(numbers: List[str]) -> Dict[str, Any]:
    """Advisory TRAI posture report for a batch of numbers. Never blocks."""
    from app.sources import in_phone

    items = []
    unscrubbed_mobiles = 0
    for raw in numbers or []:
        e164 = in_phone.to_e164(raw)
        mobile = in_phone.is_mobile(raw)
        if mobile and e164:
            unscrubbed_mobiles += 1
        items.append({
            "number": e164, "is_mobile": mobile,
            "is_landline": in_phone.is_landline(raw),
            "dnd_scrubbed": False, "sms_allowed": False,
        })
    warnings: List[str] = []
    if unscrubbed_mobiles:
        warnings.append(
            f"{unscrubbed_mobiles} mobile(s) not DND-scrubbed. Send SMS/voice "
            "only through a DLT-registered aggregator (MSG91, Gupshup, "
            "Exotel) after scrubbing — a 10-digit personal number used for "
            "bulk commercial SMS is treated as an unregistered telemarketer."
        )
    if in_quiet_hours():
        warnings.append(
            "TRAI quiet hours now (21:00–09:00 IST): hold promo SMS/voice."
        )
    return {"numbers": items, "quiet_hours_now": in_quiet_hours(), "warnings": warnings}
