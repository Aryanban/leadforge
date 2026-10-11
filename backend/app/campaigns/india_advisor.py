"""India deliverability advisor — pure checks, no enforcement.

Self-hosted rule: the operator decides, the tool only informs. Every
function here returns *advice* (a dict with ``ok``/``warnings``). Nothing
gates, blocks, pauses, or rewrites a send. The dashboard renders these as
banners and checklists; ``execute_campaign_step`` never imports this module.
"""

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


def in_quiet_hours(now: Optional[datetime] = None) -> bool:
    """True when it is currently TRAI quiet hours (21:00–09:00 IST)."""
    now = now or datetime.now(timezone.utc)
    try:
        ist = now.astimezone(ZoneInfo(IST))
    except Exception:
        ist = now
    hour = ist.hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


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
