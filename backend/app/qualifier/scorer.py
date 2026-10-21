import re
from typing import Any, Dict, List, Optional

from .signals import extract_signals

# Legacy formula preserved verbatim: used whenever no ICP profile is attached,
# so historical lead scores do not change.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "verified_email": 30,
    "any_email": 15,
    "phone": 15,
    "whatsapp": 15,
    "website": 15,
    "rating_4_5": 10,
    "rating_4_0": 5,
    "reviews_10": 10,
    "reviews_3": 5,
}

# Signals unlocked once an ICP profile exists. These layer on top of the legacy
# weights and can be overridden per-profile via ICPProfile.signal_weights.
ICP_SIGNAL_WEIGHTS: Dict[str, float] = {
    "unclaimed_gbp": 8,
    "category_match": 6,
    "social_presence": 4,
    "ssl_valid": 4,
    "site_stale": -4,
    "running_ads": 6,
}

PRESETS: Dict[str, Dict[str, float]] = {
    # Default: maximise deliverability and outreach quality.
    "outreach_quality": {**DEFAULT_WEIGHTS, **ICP_SIGNAL_WEIGHTS},
    # Agency angle: businesses with a weak web presence are the best prospects,
    # so missing/outdated assets flip from penalties into rewards.
    "agency_opportunity": {
        **DEFAULT_WEIGHTS,
        **ICP_SIGNAL_WEIGHTS,
        "unclaimed_gbp": 15,
        "site_stale": 10,
        "ssl_valid": -6,
        "running_ads": 10,
        "category_match": 8,
    },
}

STOPWORDS = {
    "in", "near", "around", "and", "with", "without", "the", "a", "of", "for",
    "looking", "want", "need", "find", "me", "please",
}


def _tokenize(text: str) -> List[str]:
    tokens = [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]


def _category_match(signals: Dict[str, Any], icp_profile: Any) -> bool:
    """True when ICP niche tokens appear in the business category or name."""
    if icp_profile is None:
        return False
    niche_tokens = set(_tokenize(getattr(icp_profile, "niche", "") or ""))
    if not niche_tokens:
        return False
    haystack = f"{signals.get('category', '')} {signals.get('name', '')}"
    hay_tokens = set(_tokenize(haystack))
    return bool(niche_tokens & hay_tokens)


def score_lead(
    business: Any,
    contacts: Optional[List[Any]] = None,
    icp_profile: Any = None,
) -> Dict[str, Any]:
    """
    Weighted 0-100 lead quality model.

    Without an ICP profile this reproduces the legacy calculate_lead_quality_score
    output exactly. With an ICP profile the additional fit/intent signals are layered
    in (optionally overridden by ICPProfile.signal_weights) and the profile preset
    decides whether weak web presence is a penalty or an opportunity.
    """
    contacts = contacts or []
    signals = extract_signals(business, contacts)

    # India source-trust overlay: self-listed directories (JustDial/IndiaMART)
    # carry shared-lead / stale-number risk; live GBP and first-party website
    # data do not. This shifts the score but never gates it — the operator
    # decides whether a lead is worth a call.
    from .source_trust import source_trust, trust_score_modifier, SOURCE_TRUST
    _source = (business.get("source") if isinstance(business, dict)
               else getattr(business, "source", None))
    if _source and str(_source).strip().lower() in SOURCE_TRUST:
        _trust, _trust_note = source_trust(_source)
        _trust_delta = trust_score_modifier(_trust)
        _trust_known = True
    else:
        # No recorded source, or a source we have no data for: stay exactly
        # on the legacy formula so historical scores do not drift.
        _trust, _trust_delta, _trust_known = 0.0, 0.0, False

    if icp_profile is not None:
        preset_name = (getattr(icp_profile, "preset", None) or "outreach_quality")
        weights = dict(PRESETS.get(preset_name, PRESETS["outreach_quality"]))
        overrides = getattr(icp_profile, "signal_weights", None)
        if isinstance(overrides, dict):
            weights.update({k: float(v) for k, v in overrides.items() if v is not None})
    else:
        weights = dict(DEFAULT_WEIGHTS)

    breakdown: Dict[str, float] = {}
    badges: List[str] = []

    def add(key: str, condition: bool, badge: Optional[str] = None) -> None:
        weight = weights.get(key)
        if weight is None:
            return
        if condition:
            breakdown[key] = weight
            if badge:
                badges.append(badge)

    add("verified_email", bool(signals["verified_email"]), "Verified Email")
    if not signals["verified_email"]:
        add("any_email", bool(signals["any_email"]), "Email Available")
    add("phone", bool(signals["phone"]), "Direct Phone")
    # The WhatsApp points now require a genuinely mobile number. The signal
    # used to be derived mechanically from the same phone string, so it could
    # never disagree with "phone" - 15 of 100 points were handed out for free
    # and a landline-only lead scored exactly like a WhatsApp-reachable one.
    # On WhatsApp (the primary channel for Indian SMBs) the distinction is
    # the whole point.
    if signals.get("whatsapp"):
        if signals.get("mobile_line"):
            add("whatsapp", True, "WhatsApp Ready")
        else:
            badges.append("Landline (no WhatsApp)")
    add("website", bool(signals["website"]), "Active Website")

    # Unclaimed listings always carry the badge (legacy behaviour); the score
    # weight only applies once an ICP profile is attached.
    if signals["unclaimed_gbp"] and "Unclaimed GBP" not in badges:
        badges.append("Unclaimed GBP")

    rating = signals["rating"]
    if rating is not None and rating >= 4.5:
        add("rating_4_5", True, "Top Rated")
    elif rating is not None and rating >= 4.0:
        add("rating_4_0", True)

    reviews = signals["reviews_count"]
    if reviews is not None and reviews >= 10:
        add("reviews_10", True, "High Reviews")
    elif reviews is not None and reviews >= 3:
        add("reviews_3", True)

    if icp_profile is not None:
        add("unclaimed_gbp", bool(signals["unclaimed_gbp"]), "Unclaimed GBP")
        add("category_match", _category_match(signals, icp_profile), "Niche Match")
        add("social_presence", bool(signals["social_presence"]), "Social Presence")
        if signals["ssl_valid"] is not None:
            add("ssl_valid", bool(signals["ssl_valid"]), "SSL Secured")
        if signals["site_stale"] is not None:
            add("site_stale", bool(signals["site_stale"]), "Stale Website")
        if signals["running_ads"] is not None:
            add("running_ads", bool(signals["running_ads"]), "Running Ads")

    score = int(sum(breakdown.values()))
    # The trust modifier is a *bounded* number in [-8, +5]. Rounding it to an
    # integer collapsed the whole range into +/-4, so IndiaMART (0.60) received
    # no discount at all while JustDial (0.50) got -2 - and the promise that
    # "a scraped-aggregator lead never outranks a primary-source one" was not
    # kept. Apply it as a float.
    score = min(100, max(10, score + _trust_delta))
    if _trust_known and _trust < 0.75:
        badges.append("Verify phone (directory-sourced)")
    elif _trust_known and _trust >= 0.90 and _source:
        badges.append(f"Trusted source: {_source}")

    if score >= 75:
        tier = "HOT"
    elif score >= 45:
        tier = "WARM"
    else:
        tier = "COLD"

    return {
        "score": score,
        "tier": tier,
        "badges": badges,
        "signal_breakdown": breakdown,
        "signals": signals,
        "source_trust": _trust if _trust_known else None,
        "trust_modifier": _trust_delta,
    }
