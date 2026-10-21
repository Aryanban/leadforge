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

#: Constraints the current filter model cannot express. When the user asks for
#: one of these and we silently ignore it, they get back a list that looks
#: like an answer but is not - the single most trust-destroying thing this
#: parser could do. So the terms are detected and reported back as warnings
#: instead of being dropped in silence.
UNSUPPORTED_TERMS = re.compile(
    r"\b("
    r"\d+\s*(?:employees?|staff|people|persons?|members?)"
    r"|revenue|turnover"
    r"|crore|cr\b|lakh|lakhs|lacs"
    r"|shopify|woocommerce|wix|wordpress|magento|gohighlevel|zoho"
    r"|founder|co-?founder|ceo|cto|cfo|coo|cmo|md|principal"
    r"|director|manager|head of|senior|junior|leadership|decision maker"
    r"|gstin|gst|udyam|msme|shop and establishment"
    r"|exporter|importer|manufacturer|wholesaler|distributor"
    r"|franchise|chain|multi-?location|branch"
    r"|funding|investor|vc|raised|seed round"
    r"|linkedin|technographic|tech stack|built with"
    r"|pincode|postal code|postcode"
    r")\b",
    re.IGNORECASE,
)

#: Leading phrases that describe the *intent*, not the industry. They used to
#: end up in the niche ("Best Leads: Dental Clinics") and in the keyword list,
#: so an ICP for dental clinics also matched every lead called "Best".
INTENT_PREFIXES = re.compile(
    r"^\s*(?:the\s+)?(?:best|top|high[\s-]?intent|hot|quality|premium|"
    r"qualified|targeted|relevant)\s+"
    r"(?:leads?|prospects?|contacts?|businesses?|companies)?\s*"
    r"(?::|-)?\s*",
    re.IGNORECASE,
)


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
    # Strip the intent phrase ("Best Leads: ") so it does not become part of
    # the industry or the keyword filter.
    niche = INTENT_PREFIXES.sub("", niche).strip(" :-,")
    if niche.lower().startswith("leads"):
        niche = niche[len("leads"):].strip().lstrip(":").strip()

    exclude_keywords: List[str] = []
    for hint in EXCLUDE_HINTS:
        # Capture ONE noun phrase. The old character class included a space,
        # so "without website and verified emails" captured the whole phrase
        # "website and verified emails" as a single exclusion.
        for m in re.finditer(
            r"\b" + re.escape(hint) + r"\s+([a-z0-9\-]{2,20})(?:\s+([a-z0-9\-]{2,20}))?",
            raw, re.IGNORECASE,
        ):
            phrase = (m.group(1) or "").strip().lower()
            second = (m.group(2) or "").strip().lower()
            # Only join the second token if it is part of the same phrase
            # ("no online presence"), never if it starts a new clause.
            if second and second not in CONNECTORS and second not in ("and", "with", "without"):
                phrase = f"{phrase} {second}"
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

    # Report the constraints we cannot honour instead of dropping them.
    unsupported = sorted({m.group(0).strip().lower() for m in UNSUPPORTED_TERMS.finditer(raw)})
    warnings: List[str] = []
    if unsupported:
        warnings.append(
            "These filters are not supported yet and were ignored: "
            + ", ".join(unsupported)
            + ". Narrow the results manually until field-level filters exist."
        )

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
        "unsupported_terms": unsupported,
        "warnings": warnings,
    }
