"""Engagement signals and the warm handoff rule for India.

Reddit/Quora/Modern-Inbound consensus for Indian B2B: WhatsApp's 90%+ open
rate makes it a *deal-progression* channel — it converts people who already
know you. Cold WhatsApp from an unknown number gets reported as spam and can
burn the number. So the only WhatsApp step LeadForge should ever surface is a
**warm handoff**: a contact who already engaged with your email.

This module is pure over stored ``Send`` rows — no network, no sends, no
gating. The campaign executor may *choose* to act on ``whatsapp_handoff``;
nothing here forces it.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

#: Opens needed before WhatsApp is worth suggesting.
HANDOFF_MIN_OPENS = 3
#: Clicks on the tracking pixel link (strong intent) downgrade the bar to 1.
HANDOFF_MIN_CLICKS = 1


def has_engaged(sends: List[Any], min_opens: int = HANDOFF_MIN_OPENS) -> bool:
    """True when the contact opened >= min_opens or clicked >= 1 email."""
    opens = sum(1 for s in sends or [] if getattr(s, "opened", False))
    clicks = sum(1 for s in sends or [] if getattr(s, "clicked", False))
    return opens >= min_opens or clicks >= HANDOFF_MIN_CLICKS


def whatsapp_handoff(sends: List[Any], has_whatsapp_link: bool) -> Dict[str, Any]:
    """Advises whether to warm-handoff this contact to WhatsApp.

    Returns ``{"suggest": bool, "reason": str, "opens", "clicks"}``.
    Suggests only for a genuinely engaged contact with a mobile number;
    never blocks, never sends.
    """
    opens = sum(1 for s in sends or [] if getattr(s, "opened", False))
    clicks = sum(1 for s in sends or [] if getattr(s, "clicked", False))
    if not has_whatsapp_link:
        return {"suggest": False, "reason": "no_mobile_number",
                "opens": opens, "clicks": clicks}
    if not has_engaged(sends):
        return {"suggest": False, "reason": "not_enough_engagement",
                "opens": opens, "clicks": clicks}
    reason = "clicked" if clicks else f"opened_{opens}_times"
    return {"suggest": True, "reason": reason, "opens": opens, "clicks": clicks}


def engagement_summary(sends: List[Any]) -> Dict[str, int]:
    """Counts across sends: sent/opened/clicked/replied/bounced."""
    out = {"sent": 0, "opened": 0, "clicked": 0, "replied": 0, "bounced": 0}
    for s in sends or []:
        if getattr(s, "status", None) == "sent":
            out["sent"] += 1
        for key in ("opened", "clicked", "replied", "bounced"):
            if getattr(s, key, False):
                out[key] += 1
    return out
