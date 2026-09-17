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
    add("whatsapp", bool(signals["whatsapp"]), "WhatsApp Ready")
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
    score = min(100, max(10, score))

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
    }
