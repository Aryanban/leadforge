import re
from typing import Any, Dict, List

LOCATION_KEYWORDS = ("in", "near", "around", "across")
CONNECTORS = {
    "with", "without", "and", "having", "that", "who", "which",
    "looking", "want", "need", "verified", "unverified",
}

EXCLUDE_HINTS = ("without", "no", "not", "excluding", "exclude")
REQUIRE_VERIFIED = ("verified email", "verified emails", "deliverable email", "verified contact")
AGENCY_HINTS = ("unclaimed", "no website", "without website", "outdated", "old website", "no online presence")
ADS_HINTS = ("running ads", "facebook ads", "ad spend", "advertising")
HIGH_INTENT_HINTS = ("high intent", "hot lead", "hot leads", "best lead", "best leads")


def _extract_area(text: str) -> str:
    """Captures a place name after a location keyword, stopping at connectors."""
    m = re.search(r"\b(" + "|".join(LOCATION_KEYWORDS) + r")\s+", text, re.IGNORECASE)
    if not m:
        return ""

    tokens = text[m.end():].split()
    area_tokens: List[str] = []
    for token in tokens:
        clean = token.strip(".,;:")
        if not clean:
            continue
        if clean.lower() in CONNECTORS:
            break
        area_tokens.append(clean)
        if len(area_tokens) >= 4:
            break

    return " ".join(area_tokens).strip(".,;:")


def _clean_tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def parse_icp_text(text: str) -> Dict[str, Any]:
    """
    Rule-based natural-language ICP parser.

    Turns free text such as "dentists in South Delhi with verified emails and no website"
    into a draft ICPProfile payload the user can refine in the wizard.
    """
    raw = (text or "").strip()

    area = _extract_area(raw)
    if area:
        m = re.search(r"\b(" + "|".join(LOCATION_KEYWORDS) + r")\s+" + re.escape(area), raw, re.IGNORECASE)
        niche = raw[: m.start()].strip() if m else raw
    else:
        niche = raw

    niche = re.sub(r"\s+", " ", niche).strip().rstrip(",").strip()
    niche = re.sub(r"^(find|get|search|show|list)\s+(me\s+)?", "", niche, flags=re.IGNORECASE).strip()
    if niche.lower().startswith("leads"):
        niche = niche[len("leads"):].strip().lstrip(":").strip()

    exclude_keywords: List[str] = []
    for hint in EXCLUDE_HINTS:
        for m in re.finditer(r"\b" + re.escape(hint) + r"\s+([a-z0-9\- ]{2,30})", raw, re.IGNORECASE):
            phrase = m.group(1).strip().lower()
            if phrase and phrase not in exclude_keywords:
                exclude_keywords.append(phrase)

    lowered = raw.lower()
    preset = "outreach_quality"
    if any(h in lowered for h in AGENCY_HINTS):
        preset = "agency_opportunity"

    signal_weights: Dict[str, float] = {}
    if any(h in lowered for h in ADS_HINTS):
        signal_weights["running_ads"] = 15
    if any(h in lowered for h in REQUIRE_VERIFIED):
        signal_weights["verified_email"] = 40

    min_score = 45
    if any(h in lowered for h in HIGH_INTENT_HINTS):
        min_score = 70
    elif any(h in lowered for h in REQUIRE_VERIFIED):
        min_score = 60

    keywords = [t for t in _clean_tokens(niche) if len(t) > 2 and t not in ("and", "with")]

    return {
        "name": raw[:80] if raw else "Untitled ICP",
        "niche": niche.title() if niche else "",
        "area": area,
        "keywords": keywords[:8],
        "exclude_keywords": exclude_keywords[:8],
        "min_score": min_score,
        "preset": preset,
        "signal_weights": signal_weights if signal_weights else None,
        "preferred_sources": None,
    }
