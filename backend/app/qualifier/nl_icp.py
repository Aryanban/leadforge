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
#:
#: The terms that are now *supported* (headcount, turnover, market tier,
#: role) are parsed into structured criteria instead, so they are listed in
#: SUPPORTED_TERMS below and do not appear here.
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

#: ---------------------------------------------------------------------------
#: Structured criteria. These are the constraints the model can now express,
#: so they are parsed out of the sentence instead of being reported as
#: unsupported.
#: ---------------------------------------------------------------------------

#: "11-50 employees", "50+ staff", "under 20 people"
_RANGE_EMPLOYEES_RE = re.compile(
    r"(\d{1,5})\s*(?:-|to|and)\s*(\d{1,5})\s*(?:employees?|staff|people|persons?|members?)",
    re.IGNORECASE,
)
_OVER_EMPLOYEES_RE = re.compile(
    r"(\d{1,5})\s*\+?\s*(?:employees?|staff|people|persons?|members?)",
    re.IGNORECASE,
)
_UNDER_EMPLOYEES_RE = re.compile(
    r"(?:under|below|less than|fewer than|up to|max(?:imum)?)\s*(\d{1,5})\s*"
    r"(?:employees?|staff|people|persons?|members?)",
    re.IGNORECASE,
)
_OVER_TURNOVER_RE = re.compile(
    r"(?:turnover|revenue)\s*(?:of\s*)?(?:over|above|more than|greater than|at least|min)?\s*"
    r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lakhs|lacs|million|crore+)?",
    re.IGNORECASE,
)
_UNDER_TURNOVER_RE = re.compile(
    r"(?:turnover|revenue)\s*(?:under|below|less than|up to)?\s*"
    r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lakhs|lacs|million)?",
    re.IGNORECASE,
)

#: "tier 2 cities", "metro", "tier-3"
_TIER_RE = re.compile(
    r"\b(?:tier[\s-]?(\d)|metro|metropolitan)\b", re.IGNORECASE
)

#: The roles an operator asks for, mapped to the seniority bands.
_ROLE_HINTS: Dict[str, List[str]] = {
    "owner": ["owner"],
    "founder": ["owner"],
    "proprietor": ["owner"],
    "promoter": ["owner"],
    "partner": ["owner"],
    "principal": ["owner"],
    "ceo": ["c_level"],
    "c-level": ["c_level"],
    "c level": ["c_level"],
    "managing director": ["c_level"],
    "md": ["c_level"],
    "chief": ["c_level"],
    "vp": ["vp"],
    "vice president": ["vp"],
    "director": ["director"],
    "head of": ["head"],
    "head": ["head"],
    "manager": ["manager"],
    "senior": ["senior"],
    "founder ceo": ["owner", "c_level"],
}

_DECISION_MAKER_RE = re.compile(
    r"\bdecision[\s-]?makers?\b|\bowners?\s+and\s+directors\b", re.IGNORECASE
)

#: The turnover bands, in rupees, matching the scorer's ladder.
_TURNOVER_BANDS: List[tuple] = [
    ("<1Cr", 0.0, 1_00_00_000.0),
    ("1-10Cr", 1_00_00_000.0, 10_00_00_000.0),
    ("10-50Cr", 10_00_00_000.0, 50_00_00_000.0),
    ("50-100Cr", 50_00_00_000.0, 100_00_00_000.0),
    ("100-500Cr", 100_00_00_000.0, 500_00_00_000.0),
    ("500Cr+", 500_00_00_000.0, None),
]

_SCALE = {
    "crore": 1_00_00_000.0, "crores": 1_00_00_000.0, "cr": 1_00_00_000.0,
    "lakh": 1_00_000.0, "lakhs": 1_00_000.0, "lac": 1_00_000.0,
    "lacs": 1_00_000.0, "million": 1_00_000.0,
}


def _band_for_amount(amount: float) -> str:
    for label, low, high in _TURNOVER_BANDS:
        if low is not None and amount < low:
            continue
        if high is not None and amount >= high:
            continue
        return label
    return _TURNOVER_BANDS[-1][0]


def _parse_structured_criteria(text: str) -> Dict[str, Any]:
    """Pulls the expressible constraints out of a sentence.

    Returns only the keys it could fill, so the caller can merge them into
    the draft profile without clobbering anything.
    """
    out: Dict[str, Any] = {}

    match = _RANGE_EMPLOYEES_RE.search(text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if low <= high:
            out["min_employees"] = low
            out["max_employees"] = high
    else:
        match = _UNDER_EMPLOYEES_RE.search(text)
        if match:
            out["max_employees"] = int(match.group(1))
        else:
            match = _OVER_EMPLOYEES_RE.search(text)
            if match:
                out["min_employees"] = int(match.group(1))

    bands: List[str] = []
    match = _OVER_TURNOVER_RE.search(text)
    if match:
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            value = 0.0
        unit = (match.group(2) or "crore").lower()
        amount = value * _SCALE.get(unit, 1_00_00_000.0)
        band = _band_for_amount(amount)
        if band not in bands:
            bands.append(band)
    if bands:
        out["revenue_bands"] = bands

    tiers: List[str] = []
    for match in _TIER_RE.finditer(text):
        tier_number = match.group(1)
        if tier_number:
            tiers.append(f"tier_{tier_number}")
        else:
            tiers.append("metro")
    if tiers:
        out["market_tiers"] = sorted(set(tiers))

    roles: List[str] = []
    lowered = text.lower()
    for hint, bands_for_hint in _ROLE_HINTS.items():
        if hint in lowered:
            for band in bands_for_hint:
                if band not in roles:
                    roles.append(band)
    if roles:
        out["seniorities"] = roles
    if _DECISION_MAKER_RE.search(text):
        out["decision_makers_only"] = True

    return out


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

    structured = _parse_structured_criteria(raw)

    # Report the constraints we cannot honour instead of dropping them.
    #
    # The terms that are now supported are excluded from the warning, and
    # the ones the parser could not fill in are reported so the operator
    # knows the draft is not the whole sentence.
    unsupported = sorted({
        m.group(0).strip().lower()
        for m in UNSUPPORTED_TERMS.finditer(raw)
        if not _is_supported_term(m.group(0).strip().lower(), structured)
    })
    warnings: List[str] = []
    if unsupported:
        warnings.append(
            "These filters are not supported yet and were ignored: "
            + ", ".join(unsupported)
            + ". Narrow the results manually until field-level filters exist."
        )

    draft = {
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
    # The structured criteria the sentence actually asked for.
    for key, value in structured.items():
        draft[key] = value
    return draft


def _is_supported_term(term: str, structured: Dict[str, Any]) -> bool:
    """Whether a detected term was turned into a structured criterion.

    A term is only "supported" if the parser actually filled in the
    matching criterion. "50 employees" fills ``min_employees``; "500
    employees" also does, but a bare "revenue" with no figure does not -
    and that one must still be reported as unsupported rather than
    silently dropped.
    """
    lowered = term.lower()
    if "employee" in lowered or "staff" in lowered or "people" in lowered:
        return "min_employees" in structured or "max_employees" in structured
    if "revenue" in lowered or "turnover" in lowered:
        return "revenue_bands" in structured
    if "crore" in lowered or "cr" in lowered or "lakh" in lowered:
        return "revenue_bands" in structured
    if any(word in lowered for word in (
        "founder", "ceo", "cfo", "coo", "cmo", "md", "principal",
        "director", "manager", "senior", "decision maker", "head of",
    )):
        return "seniorities" in structured or structured.get("decision_makers_only")
    return False
