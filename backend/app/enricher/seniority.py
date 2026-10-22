"""Person-level classification: who is this, and can we sell to them?

Apollo's People table is not a contact list - it is a *filterable* list of
humans, and the filter that matters most is seniority ("all owners" /
"all directors"). This module turns a free-text job title into a stable
band, and turns a free-text company blurb into size / revenue / tech
signals.

The title taxonomy is deliberately India-aware. An Indian SMB's decision
maker is usually "Proprietor", "Promoter", "Managing Director" or
"Principal" - none of which appear in a US/EU title list, and a
US-only taxonomy files all four as "unknown" and drops them from every
decision-maker filter.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------
# Seniority
# --------------------------------------------------------------------------

#: Ordered most senior to least. The order matters: a rule that matches
#: "vice president" must not be shadowed by a rule that matches "president".
SENIORITY_BANDS: Tuple[str, ...] = (
    "owner",
    "c_level",
    "vp",
    "director",
    "head",
    "manager",
    "senior",
    "staff",
    "other",
    "unknown",
)

#: Titles that carry real buying authority in an Indian SMB.
_OWNER_TITLES = (
    "owner", "founder", "co-founder", "cofounder", "proprietor", "promoter",
    "partner", "principal", "sole proprietor", "proprietor-cum",
    "managing partner", "managing proprietor", "chairman", "chairperson",
    "chairman-cum",
)

_C_LEVEL_TITLES = (
    "chief executive officer", "ceo", "chief operating officer", "coo",
    "chief financial officer", "cfo", "chief information officer", "cio",
    "chief technology officer", "cto", "chief marketing officer", "cmo",
    "chief hr", "chro", "chief human resources", "chief administrative",
    "chief", "managing director", "md", "executive director",
    "whole time director", "wtd", "joint managing director",
)

_VP_TITLES = (
    "vice president", "vp", "vice chairperson", "vice chairman",
    "deputy managing director", "deputy director",
)

_DIRECTOR_TITLES = (
    "director", "non-executive director", "board member", "company secretary",
)

_HEAD_TITLES = (
    "head of", "sr head", "senior head", "group head", "practice head",
    "center head", "centre head", "national head", "zonal head", "state head",
    "regional head", "unit head", "branch head", "vertical head",
)

_MANAGER_TITLES = (
    "general manager", "senior manager", "general sales manager",
    "sales manager", "operations manager", "project manager", "product manager",
    "marketing manager", "finance manager", "hr manager", "accounts manager",
    "office manager", "store manager", "branch manager", "regional manager",
    "territory manager", "area manager", "plant manager", "facility manager",
    "practice manager", "service manager", "purchase manager",
    "procurement manager", "business development manager", "bd manager",
    "manager",
)

_SENIOR_TITLES = (
    "senior consultant", "senior engineer", "senior analyst", "senior associate",
    "senior executive", "senior specialist", "senior designer", "senior officer",
    "senior manager", "lead consultant", "lead engineer", "team lead",
    "tech lead", "principal consultant", "principal engineer",
    "principal associate",
)


def _word_pattern(alternatives) -> "re.Pattern":
    """Matches a title phrase on word boundaries.

    Plain substring matching is a trap here: ``"director"`` contains
    ``"cto"``, so every director in India was being filed as a C-level
    executive. Substring matching also files ``"md"`` inside ``"admin"``
    and ``"ceo"`` inside ``"recentre"``.
    """
    parts = []
    for alt in alternatives:
        escaped = re.escape(alt).replace(r"\ ", r"\s+")
        parts.append(rf"\b{escaped}\b")
    if not parts:
        return re.compile(r"(?!x)x")  # never matches
    return re.compile("|".join(parts), re.IGNORECASE)


_OWNER_RE = _word_pattern(_OWNER_TITLES)
_C_LEVEL_RE = _word_pattern(_C_LEVEL_TITLES)
_VP_RE = _word_pattern(_VP_TITLES)
_DIRECTOR_RE = _word_pattern(_DIRECTOR_TITLES)
_HEAD_RE = _word_pattern(_HEAD_TITLES)
_MANAGER_RE = _word_pattern(_MANAGER_TITLES)
_SENIOR_RE = _word_pattern(_SENIOR_TITLES)

#: Titles that are not a person at all.
_NON_PERSON_TITLES = (
    "sales", "support", "info", "contact", "admin", "office", "help",
    "enquiry", "enquiry", "inquiry", "career", "careers", "hr", "no reply",
    "noreply", "do not reply", "donotreply", "team", "team sales",
)

#: Words that make a string a company rather than a person.
_COMPANY_HINTS = (
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "corp",
    "corporation", "company", "co.", "&", "and", "enterprises", "industries",
    "traders", "ventures", "group", "holdings", "associates", "partners",
    "clinic", "hospital", "centre", "center", "academy", "institute",
    "hospitality", "restaurant", "hotel", "agency", "store", "shop",
    "solutions", "services", "systems", "technologies", "consultants",
)


def _norm(title: Optional[str]) -> str:
    if not title:
        return ""
    text = str(title).lower().strip()
    # "S K M D" and "S.K.M.D." are how Indian sites write "SK MD". Collapse
    # runs of single letters into two-letter pairs so the abbreviation
    # survives as a word the matcher can see.
    def _pair_up(match):
        letters = re.sub(r"[^a-z]", "", match.group(0))
        return " ".join(letters[i:i + 2] for i in range(0, len(letters), 2))

    text = re.sub(r"\b[a-z](?:[\s.]+[a-z])+\b", _pair_up, text)
    text = re.sub(r"[^a-z0-9&+\-\s/]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_role_account_title(title: Optional[str]) -> bool:
    """Whether a "title" is really a role mailbox label, not a person."""
    text = _norm(title)
    if not text:
        return False
    if text in _NON_PERSON_TITLES:
        return True
    return any(text.startswith(prefix) for prefix in ("sales", "info", "support"))


def classify_seniority(title: Optional[str]) -> str:
    """Maps a job title onto a seniority band.

    Returns one of :data:`SENIORITY_BANDS`. ``"unknown"`` means the title
    was empty or unrecognised - never guessed, because a wrong band is
    worse than no band: it silently puts a clerk in a "decision maker"
    filter.
    """
    text = _norm(title)
    if not text:
        return "unknown"

    # Ordered most senior to least, so "Senior Manager" lands on senior
    # and "Managing Director" on C-level.
    if _OWNER_RE.search(text):
        return "owner"
    if _C_LEVEL_RE.search(text):
        return "c_level"
    if _VP_RE.search(text):
        return "vp"
    if _HEAD_RE.search(text):
        return "head"
    if _DIRECTOR_RE.search(text):
        return "director"
    if _SENIOR_RE.search(text):
        return "senior"
    if _MANAGER_RE.search(text):
        return "manager"
    if re.search(r"\bstaff\b|\bassociate\b|\bexecutive\b|\bofficer\b|\bcoordinator\b", text):
        return "staff"
    if re.search(r"\bprincipal\b", text):
        # A "Principal" at a school or a CA firm is a decision maker.
        return "owner"
    return "other"


def is_decision_maker(seniority: Optional[str]) -> bool:
    """Whether a band carries real buying authority."""
    return (seniority or "") in {
        "owner", "c_level", "vp", "director", "head",
    }


#: Bands a "decision maker" filter should include by default.
DECISION_MAKER_BANDS: Tuple[str, ...] = ("owner", "c_level", "vp", "director", "head")

#: Human labels for the dashboard.
SENIORITY_LABELS: Dict[str, str] = {
    "owner": "Owner / Founder",
    "c_level": "C-Level / MD",
    "vp": "VP / Deputy MD",
    "director": "Director",
    "head": "Head of Function",
    "manager": "Manager",
    "senior": "Senior / Lead",
    "staff": "Staff / Associate",
    "other": "Other",
    "unknown": "Unknown",
}


def looks_like_person_name(name: Optional[str]) -> bool:
    """Whether a string looks like a human's name rather than a company.

    The contact row's first/last name is the thing a salesperson filters
    on, so "Acme Dental Pvt Ltd" in that field is a data error worth
    catching at the point of extraction.
    """
    if not name:
        return False
    text = str(name).strip()
    if len(text) < 3 or len(text) > 60:
        return False
    lowered = text.lower()
    if any(hint in lowered for hint in _COMPANY_HINTS):
        return False
    if any(ch.isdigit() for ch in text):
        return False
    words = text.split()
    if not (1 <= len(words) <= 4):
        return False
    return all(w[:1].isupper() or w.lower() in {"of", "and", "de", "da"} for w in words if w)


# --------------------------------------------------------------------------
# Company size, revenue, technology
# --------------------------------------------------------------------------

#: Revenue bands, in rupees. Apollo-style bucketing, Indian scale.
REVENUE_BANDS: Tuple[Tuple[str, Optional[float], Optional[float]], ...] = (
    ("<1Cr", 0.0, 1_00_00_000.0),
    ("1-10Cr", 1_00_00_000.0, 10_00_00_000.0),
    ("10-50Cr", 10_00_00_000.0, 50_00_00_000.0),
    ("50-100Cr", 50_00_00_000.0, 100_00_00_000.0),
    ("100-500Cr", 100_00_00_000.0, 500_00_00_000.0),
    ("500Cr+", 500_00_00_000.0, None),
)

#: The word forms people actually write, mapped to a rupee amount.
_SCALE_WORDS = {
    "lakh": 1_00_000.0, "lakhs": 1_00_000.0, "lac": 1_00_000.0, "lacs": 1_00_000.0,
    "crore": 1_00_00_000.0, "crores": 1_00_00_000.0, "cr": 1_00_00_000.0,
    "crs": 1_00_00_000.0, "k": 1_000.0, "thousand": 1_000.0,
    "m": 1_00_000.0, "million": 1_00_000.0, "mn": 1_00_000.0,
    "b": 1_00_00_000.0, "billion": 1_00_00_000.0, "bn": 1_00_00_000.0,
}

#: "annual turnover of 12 cr", "revenue: 40 lakhs", "turnover rs 2.5 crore".
_TURNOVER_RE = re.compile(
    r"(?:turnover|revenue|annual\s+(?:turnover|revenue|sales)|sales\s+turnover|"
    r"top\s+line|gmv|annual\s+billing|billing)"
    r"[^\d₹$]{0,24}(?:rs\.?|inr|₹|\$)?\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r"(lakh|lakhs|lac|lacs|crore|crores|cr|crs|k|thousand|m|million|mn|b|billion|bn)?",
    re.IGNORECASE,
)

#: "team of 50", "50+ employees", "we are a 30-person company".
_EMPLOYEE_RE = re.compile(
    r"(\d{1,7})\s*(?:\+\s*)?(?:[- ]?\s*)?(?:"
    r"employees|staff|people|members|team|professionals|persons|"
    r"associates|employees\s+strong|person\s+company"
    r")",
    re.IGNORECASE,
)

_EMPLOYEE_BEFORE_RE = re.compile(
    r"(?:team\s+of|staff\s+of|group\s+of|workforce\s+of|we\s+are\s+|company\s+of\s+)"
    r"\s*(\d{1,7})\b",
    re.IGNORECASE,
)

#: Technologies worth knowing about for an Indian SMB.
_TECH_SIGNATURES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Shopify", ("shopify",)),
    ("WooCommerce", ("woocommerce",)),
    ("Magento", ("magento",)),
    ("BigCommerce", ("bigcommerce",)),
    ("Wix", ("wix.com", "wixstore", "wix ")),
    ("WordPress", ("wordpress", "wp-content", "wp-json")),
    ("Webflow", ("webflow",)),
    ("Squarespace", ("squarespace",)),
    ("Zoho", ("zoho",)),
    ("Odoo", ("odoo",)),
    ("Tally", ("tally",)),
    ("Khatabook", ("khatabook",)),
    ("Kylas", ("kylas",)),
    ("LeadSquared", ("leadsquared",)),
    ("Freshworks", ("freshworks", "freshdesk")),
    ("Zendesk", ("zendesk",)),
    ("HubSpot", ("hubspot",)),
    ("Salesforce", ("salesforce",)),
    ("Pipedrive", ("pipedrive",)),
    ("IndiaMART", ("indiamart",)),
    ("JustDial", ("justdial",)),
    ("Sulekha", ("sulekha",)),
    ("Practo", ("practo",)),
    ("Google Analytics", ("google-analytics", "gtag.js", "ga('create'")),
    ("Google Ads", ("googlesyndication", "adsbygoogle", "googleadservices")),
    ("Meta Pixel", ("fbevents.js", "connect.facebook.net", "facebook.com/tr")),
    ("Razorpay", ("razorpay",)),
    ("PayU", ("payu",)),
    ("Cashfree", ("cashfree",)),
    ("PhonePe", ("phonepe",)),
    ("Paytm", ("paytm",)),
    ("Amazon Pay", ("amazonpay",)),
    ("Twilio", ("twilio",)),
    ("Intercom", ("intercom",)),
    ("HubSpot Forms", ("hsforms", "hubspot.com/forms")),
)

#: A company with more than this many employees is not an SMB in the sense
#: this product targets.
SMB_EMPLOYEE_CEILING = 500


def parse_employee_count(text: Optional[str]) -> Optional[int]:
    """Pulls a headcount out of a company blurb.

    Only accepts a number that is explicitly attached to a people-word, so
    a stray "2024" in a copyright line is not read as a headcount.
    """
    if not text:
        return None
    blob = str(text)[:20000]

    best = None
    for match in _EMPLOYEE_RE.finditer(blob):
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 1_00_000:
            best = value
    for match in _EMPLOYEE_BEFORE_RE.finditer(blob):
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 1_00_000:
            best = value
    return best


def parse_revenue(text: Optional[str]) -> Optional[float]:
    """Pulls an annual revenue figure in rupees out of a company blurb."""
    if not text:
        return None
    blob = str(text)[:20000]

    for match in _TURNOVER_RE.finditer(blob):
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        unit = (match.group(2) or "").lower()
        multiplier = _SCALE_WORDS.get(unit)
        if multiplier is None:
            # A bare number after the keyword: assume crores when the
            # number is small, which is how it is written in India.
            multiplier = 1_00_00_000.0 if value < 1000 else 1.0
        total = value * multiplier
        if 1_00_000.0 <= total <= 1_00_00_00_00_000.0:
            return total
    return None


def revenue_band(amount: Optional[float]) -> Optional[str]:
    """The band label for a rupee amount."""
    if amount is None:
        return None
    for label, low, high in REVENUE_BANDS:
        if low is not None and amount < low:
            continue
        if high is not None and amount >= high:
            continue
        return label
    return REVENUE_BANDS[-1][0]


def detect_technologies(html_or_text: Optional[str]) -> List[str]:
    """Technology names visible in a page's markup or text.

    Deliberately conservative: a technology is only reported when its
    fingerprint actually appears, because a guessed stack is worse than
    an absent one.
    """
    if not html_or_text:
        return []
    blob = str(html_or_text).lower()
    found: List[str] = []
    for name, signatures in _TECH_SIGNATURES:
        if any(sig.lower() in blob for sig in signatures):
            found.append(name)
    return found


def size_bucket(employee_count: Optional[int]) -> Optional[str]:
    """Apollo-style company-size buckets."""
    if employee_count is None:
        return None
    if employee_count <= 1:
        return "1"
    if employee_count <= 10:
        return "2-10"
    if employee_count <= 50:
        return "11-50"
    if employee_count <= 200:
        return "51-200"
    if employee_count <= 500:
        return "201-500"
    return "500+"


def enrich_person_fields(
    title: Optional[str],
    company_text: Optional[str] = None,
) -> Dict[str, object]:
    """Everything the People table needs about one person and their company.

    Returns a dict of column-ready values; every key is optional so the
    caller can pass it straight to the ORM.
    """
    out: Dict[str, object] = {}
    band = classify_seniority(title)
    out["seniority"] = band
    out["is_decision_maker"] = is_decision_maker(band)

    if company_text:
        employees = parse_employee_count(company_text)
        if employees is not None:
            out["employee_count"] = employees
            out["size_bucket"] = size_bucket(employees)
        revenue = parse_revenue(company_text)
        if revenue is not None:
            out["revenue"] = revenue
            out["revenue_band"] = revenue_band(revenue)
    return out


def unique_technologies(values: Optional[Set[str]]) -> List[str]:
    return sorted(v for v in (values or set()) if v)


# --------------------------------------------------------------------------
# Company profile
# --------------------------------------------------------------------------


def extract_company_profile(page_html: Optional[str]) -> Dict[str, Any]:
    """Company size, revenue and technology, read off the company's site.

    This is what makes an ICP expressible as "11-50 employees, over 10Cr
    turnover, uses Shopify" - the attributes Apollo filters on and that a
    LeadForge lead row had no column for.

    The signals are only reported when the page actually states them. A
    guessed headcount is worse than a blank one: it would put a business
    into a segment it does not belong to, and the operator would never
    know.
    """
    out: Dict[str, Any] = {}
    if not page_html:
        return out

    # Strip the markup: headcount and turnover are written in prose, and
    # script tags carry numbers that are not the company's.
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(page_html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = str(page_html)

    employees = parse_employee_count(text)
    if employees is not None:
        out["employee_count"] = employees
        out["size_bucket"] = size_bucket(employees)

    revenue = parse_revenue(text)
    if revenue is not None:
        out["revenue"] = revenue
        out["revenue_band"] = revenue_band(revenue)

    technologies = detect_technologies(page_html)
    if technologies:
        out["technologies"] = technologies

    return out
