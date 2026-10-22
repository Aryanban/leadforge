"""Finding the human behind a business on its own website.

This is the difference between a business directory and a people database.
Discovery finds a company; the decision maker is written on the company's
own "About us" or "Contact" page, and the job is to read it out.

Three signals, in descending order of reliability:

1. **JSON-LD** - ``schema.org/Person`` with a ``jobTitle``, or an
   ``Organization`` whose ``employee`` / ``founder`` / ``member`` has one.
   Structured, so it is trusted outright.
2. **Name-then-title** - "Rakesh Gupta - Proprietor". The common form.
3. **Title-then-name** - "Proprietor: Mr. Rakesh Gupta". Equally common on
   Indian sites, and the form the old pattern missed entirely.

The vocabulary is India-aware. "Proprietor", "Promoter", "Managing
Director", "Principal" and "Partner" are how Indian SMBs name the person
who can sign off; a US/EU title list files all five as unknown, and an
unknown title is a founder the People table cannot show you.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

#: Honorifics that prefix an Indian or British name.
HONORIFICS = (
    "mr", "mrs", "ms", "miss", "dr", "prof", "shri", "smt", "sri", "er",
    "ca", "cs", "adv",
)

#: Titles that identify the person who can decide.
#: "Head of Sales", "Head of Operations" - the most common Indian SMB
#: senior title, and the one a truncated pattern loses.
_HEAD_FUNCTIONS = (
    "sales", "marketing", "operations", "finance", "hr", "human resources",
    "business", "technology", "it", "development", "growth", "customer",
    "customer service", "accounts", "accounting", "product", "quality",
    "projects", "project", "support", "admin", "administration", "purchase",
    "procurement", "production", "operations", "engineering", "design",
    "digital", "strategy", "commercial", "supply chain", "manufacturing",
)

#: Compound titles that a plain alternation truncates.
_COMPOUND_TITLES = (
    "founder & ceo", "founder and ceo", "ceo & founder", "ceo and founder",
    "founder & managing director", "founder and managing director",
    "chairman & md", "chairman and md", "chairman & managing director",
    "proprietor & director", "proprietor and director", "partner & founder",
    "owner & managing director", "owner and managing director",
    "owner & director", "owner and director", "promoter & director",
    "managing director & founder", "principal consultant",
    "vice chairman & managing director",
)

DECISION_TITLES: Tuple[str, ...] = tuple(
    list(_COMPOUND_TITLES)
    + [f"head of {f}" for f in _HEAD_FUNCTIONS]
    + [f"vp {f}" for f in _HEAD_FUNCTIONS]
    + [
    # Owner level
    "owner", "founder", "co-founder", "cofounder", "proprietor",
    "sole proprietor", "promoter", "partner", "managing partner",
    "principal", "sole trader", "proprietor-cum", "chairman", "chairperson",
    # C-level
    "chief executive officer", "ceo", "chief operating officer", "coo",
    "chief financial officer", "cfo", "chief information officer", "cio",
    "chief technology officer", "cto", "chief marketing officer", "cmo",
    "chief human resources officer", "chro", "chief administrative officer",
    "managing director", "executive director", "whole time director",
    "joint managing director", "md",
    # VP / Director
    "vice president", "vp", "vice chairman", "deputy managing director",
    "director", "executive director", "joint director", "whole-time director",
    "company secretary", "board member", "board of directors",
    # Head of function
    "head of", "group head", "national head", "regional head", "state head",
    "zonal head", "branch head", "practice head", "unit head", "vertical head",
    "center head", "centre head", "head -", "chief of staff",
    # Managers
    "general manager", "sales manager", "operations manager",
    "product manager", "project manager", "marketing manager",
    "finance manager", "hr manager", "business development manager",
    "office manager", "plant manager", "practice manager", "store manager",
    "branch manager", "territory manager", "regional manager",
    "area manager", "service manager", "purchase manager",
    "procurement manager", "facility manager", "admin manager",
    # Professional
    "doctor", "dr", "dentist", "physician", "surgeon", "pharmacist",
    "lawyer", "advocate", "attorney", "architect", "engineer", "designer",
    "consultant", "accountant", " chartered accountant", "ca",
    # Sales / commercial
    "sales executive", "business development", "bd", "sales head",
    "business head", "growth head", "marketing head",
    ]
)

#: Boilerplate that shows up around a title but is not a person.
_NOT_A_PERSON_NAME = frozenset({
    "read more", "learn more", "view more", "see more", "click here",
    "call now", "call us", "book now", "book appointment", "book online",
    "get in touch", "contact us", "join us", "about us", "our services",
    "why choose us", "our team", "the team", "meet the team", "our story",
    "privacy policy", "terms of use", "terms and conditions", "refund policy",
    "success stories", "client reviews", "our clients", "our projects",
    "request a quote", "request callback", "send a message", "live chat",
    "chat with us", "more info", "know more", "explore more", "shop now",
    "order now", "buy now", "download", "download now", "apply now",
    "our vision", "our mission", "our values", "quality assurance",
    "24x7", "24 hours", "open now", "closed now", "business hours",
    "our clients", "our story", "our promise", "our approach",
})

#: A title that is really a department, not a job.
_NOT_A_TITLE = frozenset({
    "sales", "support", "info", "contact", "admin", "office", "help",
    "enquiry", "inquiry", "career", "careers", "hr", "no reply", "noreply",
    "do not reply", "donotreply", "team", "team sales", "customer care",
    "customer support", "business", "service", "services", "products",
})


#: "Dr. Aniket Kasodekar is an Orthodontist" - the role is in a verb
#: phrase rather than after a dash.
_IS_A_TITLE_RE = re.compile(
    r"((?:(?:Mr|Mrs|Ms|Dr|Prof|Shri|Smt)\.?[ \t]+)?[A-Z][a-zA-Z]*(?:[ \t]+[A-Z][a-zA-Z.]*){1,2})"
    r"[ \t]+(?:is|was|works as|serves as|served as)[ \t]+"
    r"(?:an?|the)?[ \t]*([A-Za-z][A-Za-z ]{2,28}?)(?=[,.;:()]|[ \t]+(?:and|with|in|at|of|for)[ \t]|$)",
    re.IGNORECASE,
)

#: "Mr. Nilesh Barot" - a person with an honorific but no stated role.
#:
#: These are real people, which is what the People table needs, but their
#: role is unknown, so they are recorded with an empty title and flagged
#: so the UI can say "role unknown" rather than invent one.
_HONORIFIC_NAME_RE = re.compile(
    r"\b((?:Mr|Mrs|Ms|Dr|Prof|Shri|Smt)\.?[ \t]+"
    r"[A-Z][a-zA-Z]+(?:[ \t]+[A-Z][a-zA-Z.]*){0,2})"
)

#: A role stated after "is a/an" that is too vague to be a job title.
_VAGUE_ROLES = frozenset({
    "person", "personnel", "team member", "member", "people", "human",
    "one", "part", "addition", "charge", "case", "fact", "name", "order",
    "way", "word", "time", "house", "service", "business", "company",
    "professional", "guest", "visitor", "customer", "client", "user",
    "individual", "friend", "relative", "neighbour", "neighbor",
})

#: Marketing superlatives. "Home Management is the Most Trustable Name in
#: Ahmedabad" is a slogan, not a job title.
_ROLES_NOT_ROLES = (
    "most", "best", "leading", "top", "no.1", "no 1", "number one",
    "trusted", "trustable", "premier", "number", "one", "name", "brand",
    "favorite", "favourite", "popular", "famous", "first", "only",
    "trusted name", "trusted brand",
)

#: Professions that are real roles even though they are not job titles.
PROFESSIONS = frozenset({
    "dentist", "orthodontist", "pediatrician", "physician", "surgeon",
    "cardiologist", "dermatologist", "gynaecologist", "gynecologist",
    "psychiatrist", "pharmacist", "optometrist", "radiologist", "pathologist",
    "nutritionist", "physiotherapist", "veterinarian", "lawyer", "advocate",
    "attorney", "accountant", "chartered accountant", "company secretary",
    "architect", "designer", "interior designer", "civil engineer",
    "mechanical engineer", "electrical engineer", "software engineer",
    "developer", "consultant", "realtor", "broker", "property advisor",
    "teacher", "professor", "lecturer", "trainer", "chef", "baker",
    "hotelier", "event manager", "wedding planner", "photographer",
    "videographer", "editor", "journalist", "banker", "insurance agent",
    "financial advisor", "wealth advisor", "agent", "distributor",
    "wholesaler", "retailer", "manufacturer", "exporter", "importer",
    "supplier", "contractor", "builder", "decorator", "fabricator",
    "printer", "specialist", "consultant", "marketer", "estimator",
    "surveyor", "electrician", "plumber", "carpenter", "mason", "painter",
    "beautician", "stylist", "technician", "mechanic", "electrician",
    "doctor", "surgeon", "nurse", "therapist", "counsellor", "counselor",
    "instructor", "administrator", "secretary", "receptionist", "clerk",
    "operator", "technician", "engineer", "planner", "coordinator",
})

#: Pronouns and verbs that a name group must never contain. The name
#: pattern can start mid-sentence, so "Dr. Danish and his team is
#: excellent" was read as the person "Laser Specialist. He".
_NOT_NAME_WORDS = frozenset({
    "he", "she", "it", "they", "we", "you", "i", "his", "her", "their",
    "our", "your", "my", "is", "was", "are", "were", "be", "been", "being",
    "and", "or", "but", "the", "a", "an", "this", "that", "these", "those",
    "known", "known", "known", "who", "which", "what", "when", "where",
    "who's", "there", "here", "not", "no", "yes", "if", "then", "than",
})


def _clean_name(raw: str) -> str:
    """Normalises a candidate person name."""
    name = re.sub(r"\s+", " ", (raw or "").strip())
    # Drop a leading honorific: "Mr. Rakesh Gupta" -> "Rakesh Gupta".
    name = re.sub(
        r"^(?:%s)\b\.?\s+" % "|".join(HONORIFICS), "", name, flags=re.IGNORECASE
    )
    # Drop a trailing honorific: "Rakesh Gupta (MD)".
    name = re.sub(r"\s*\((?:%s)\)\s*$" % "|".join(HONORIFICS), "", name,
                  flags=re.IGNORECASE)
    return name.strip(" ,;:-–—|()")


#: Single words that are a job title, and so cannot start a person's name.
#: Without this, "Head of Sales" + "Pooja Nair" reads as a person called
#: "Sales Pooja Nair".
_TITLE_WORDS: Set[str] = set()
for _t in DECISION_TITLES:
    for _w in re.split(r"[\s\-/]+", _t):
        if len(_w) > 2:
            _TITLE_WORDS.add(_w.lower())
_TITLE_WORDS.update({"sales", "owner", "director", "partner", "head"})


#: Business-descriptor words. A "name" containing one of these is a
#: company, not a person - "Krupa Dental Care" is not a person called
#: "Krupa".
_BUSINESS_WORDS = frozenset({
    "care", "dental", "clinic", "clinics", "polyclinic", "hospital",
    "pharmacy", "medical", "doctor", "doctors", "diagnostic", "diagnostics",
    "health", "healthcare", "wellness", "hospitality", "agency", "academy",
    "school", "college", "institute", "foundation", "associates", "consultancy",
    "consultants", "solutions", "systems", "technologies", "industries",
    "enterprises", "builders", "constructions", "construction", "properties",
    "property", "realty", "estate", "estates", "motors", "traders", "stores",
    "hotels", "resorts", "travels", "tours", "foods", "restaurants", "cafe",
    "bakery", "salon", "studios", "labs", "laboratories", "optics", "interiors",
    "engineers", "engineering", "textiles", "garments", "pharma", "chemicals",
    "electronics", "furniture", "jewellers", "jewelers", "academy", "kitchen",
    "kitchens", "interior", "exteriors", "surgical", "physio", "physiotherapy",
    "nutrition", "diet", "yoga", "gym", "fitness", "co", "company", "pvt",
    "ltd", "llp", "inc", "corp",
})

#: Page furniture that contains *customers*, not staff. A testimonial
#: reading "I bought my office from Mr. Omkar" would otherwise add a
#: customer to the People table.
_TESTIMONIAL_MARKERS = (
    "testimonial", "review", "feedback", "client-say", "clientsay",
    "customer-say", "customersay", "what-our-client", "what-our-customer",
    "success-story", "successstory", "rating", "comment", "testimonial-slider",
)


def _strip_testimonials(soup: BeautifulSoup) -> None:
    """Removes review and testimonial blocks from the tree, in place."""
    for marker in _TESTIMONIAL_MARKERS:
        for el in soup.select(f'[class*="{marker}"], [id*="{marker}"]'):
            el.decompose()
    for el in soup.find_all("blockquote"):
        el.decompose()


def _role_is_plausible(role: str) -> bool:
    """Whether a stated role is really a job, not a slogan.

    "Home Management is the Most Trustable Name in Ahmedabad" is marketing
    copy; the role here is "Most Trustable Name", which is not a job.
    """
    if not role:
        return False
    lowered = role.lower().strip(" .,;:-")
    if not lowered or lowered in _VAGUE_ROLES:
        return False
    if any(bad in lowered for bad in _ROLES_NOT_ROLES):
        return False
    words = lowered.split()
    if not (1 <= len(words) <= 3):
        return False
    if any(w in _NOT_NAME_WORDS for w in words):
        return False
    if lowered in _NOT_A_TITLE:
        return False

    from app.enricher.seniority import classify_seniority

    if classify_seniority(role) != "unknown":
        return True
    # Not a job title, but it may still be a profession.
    return any(w in PROFESSIONS for w in words)


def _trim_company_words(name: str, company_name: Optional[str] = None) -> str:
    """Strips company words from the ends of a candidate name.

    "Pundits ANERI MEHTA Co" is a person's name with the company's name
    glued to the front and its legal suffix to the back. The person is
    "ANERI MEHTA".

    The company's own name is the strongest signal, so when it is known
    its words are trimmed first: "Pundits" is in "Real Estate Pundits".
    """
    words = name.split()

    if company_name:
        company_words = {w.lower().strip(".,") for w in company_name.split()}
        while words and words[0].lower().strip(".,") in company_words:
            words = words[1:]
        while words and words[-1].lower().strip(".,") in company_words:
            words = words[:-1]

    while words and words[0].lower().strip(".,") in _BUSINESS_WORDS:
        words = words[1:]
    while words and words[-1].lower().strip(".,") in _BUSINESS_WORDS:
        words = words[:-1]
    return " ".join(words)


def is_plausible_person_name(name: str) -> bool:
    """Whether a candidate looks like a human's name.

    Two or three capitalised tokens, no digits, no company words, not a
    known call-to-action phrase, and not starting with a job title.
    """
    if not name:
        return False
    name = name.strip()
    if len(name) < 3 or len(name) > 60:
        return False
    if name.lower() in _NOT_A_PERSON_NAME:
        return False
    if any(ch.isdigit() for ch in name):
        return False

    words = [w for w in re.split(r"\s+", name) if w]
    if not (2 <= len(words) <= 4):
        return False
    if any(w.lower().strip(".,") in _NOT_NAME_WORDS for w in words):
        return False
    if not all(w[:1].isupper() or w.lower() in {"of", "and", "de", "da", "bin", "b."}
               for w in words):
        return False
    if words[0].lower().strip(".,") in _TITLE_WORDS:
        return False
    if any(w.lower().strip(".,") in _BUSINESS_WORDS for w in words):
        return False

    # Company-ish words disqualify a "name".
    company_words = (
        "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "corp",
        "corporation", "company", "enterprises", "industries", "traders",
        "ventures", "group", "holdings", "associates", "partners", "clinic",
        "hospital", "centre", "center", "academy", "institute", "hospitality",
        "restaurant", "hotel", "agency", "store", "shop", "solutions",
        "services", "systems", "technologies", "consultants", "hospitality",
        "&", "and",
    )
    lowered = [w.lower().strip(".,") for w in words]
    if any(w in company_words for w in lowered):
        return False
    return True


def _title_alternation() -> str:
    """The title vocabulary as a regex alternation, longest first.

    Longest first matters: "managing director" must win over "director",
    or every MD is filed as a plain director.
    """
    ordered = sorted(set(DECISION_TITLES), key=len, reverse=True)
    return "|".join(re.escape(t) for t in ordered)


#: "Rakesh Gupta - Proprietor" / "Rakesh Gupta, MD" / "Rakesh Gupta (Owner)"
#:
#: The name group is deliberately restricted to same-line words. With ``\s``
#: it happily ran across a line break and read "Head of Sales" + "Pooja
#: Nair - Director" as a person called "Sales Pooja Nair", and
#: "Mr. Rakesh Gupta" + "MD" as "Rakesh Gupta MD".
_NAME_THEN_TITLE_RE = re.compile(
    r"([A-Z][a-zA-Z]*(?:[ \t]+[A-Z][a-zA-Z.]*){1,3})[ \t]*"
    r"(?:[-\u2013\u2014\u2022|,:;()]|\bis\b|\bas\b|&)[ \t]*"
    r"((?:%s)\b)" % _title_alternation(),
    re.IGNORECASE,
)

#: "Proprietor: Rakesh Gupta" / "MD - Rakesh Gupta"
_TITLE_THEN_NAME_RE = re.compile(
    r"\b((?:%s)\b)[ \t]*[:\-\u2013\u2014][ \t]*"
    r"((?:(?:Mr|Mrs|Ms|Dr|Prof|Shri|Smt)\.?[ \t]+)?"
    r"[A-Z][a-zA-Z]*(?:[ \t]+[A-Z][a-zA-Z.]*){0,2})"
    % _title_alternation(),
    re.IGNORECASE,
)


#: Words that stay lower-case inside a title.
_TITLE_CONNECTORS = {"of", "and", "the", "for", "in", "at", "to", "&", "de", "da"}


def _canonical_title(raw: str) -> str:
    """Normalises a title for display and classification.

    "head of sales" -> "Head of Sales", "founder & ceo" -> "Founder & CEO".
    Acronyms keep their capitals, and connectors stay lower-case - a plain
    ``.title()`` turns "CEO" into "Ceo", which no longer matches a title
    list.
    """
    title = re.sub(r"\s+", " ", (raw or "").strip())
    title = title.strip(" ,;:-–—|()")
    if not title:
        return title
    words = []
    for word in title.split(" "):
        bare = word.strip(".,")
        if bare in _TITLE_CONNECTORS:
            words.append(bare)
        elif bare.isupper() and 2 <= len(bare) <= 5:
            words.append(bare)
        else:
            words.append(bare.capitalize())
    return " ".join(words)


def extract_executives_from_text(
    text: str,
    company_name: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Finds "name + title" pairs in a block of page text."""
    found: List[Dict[str, str]] = []
    seen: Set[str] = set()
    if not text:
        return found

    for match in _NAME_THEN_TITLE_RE.finditer(text):
        name = _trim_company_words(_clean_name(match.group(1)), company_name)
        title = _canonical_title(match.group(2))
        if not is_plausible_person_name(name):
            continue
        if title.lower() in _NOT_A_TITLE:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append({"name": name, "title": title})

    for match in _TITLE_THEN_NAME_RE.finditer(text):
        name = _trim_company_words(_clean_name(match.group(2)), company_name)
        title = _canonical_title(match.group(1))
        if not is_plausible_person_name(name):
            continue
        if title.lower() in _NOT_A_TITLE:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append({"name": name, "title": title})

    # "Dr. Aniket Kasodekar is an Orthodontist"
    for match in _IS_A_TITLE_RE.finditer(text):
        name = _trim_company_words(_clean_name(match.group(1)), company_name)
        role = match.group(2).strip()
        if not is_plausible_person_name(name):
            continue
        if not _role_is_plausible(role):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append({"name": name, "title": _canonical_title(role)})

    return found


def extract_people_without_roles(
    text: str,
    company_name: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Finds people named with an honorific but no stated role.

    Recorded with an empty title, because a person with an unknown role is
    still a person - and "we know there is a decision maker here but not
    which one" is exactly what an operator needs to see.
    """
    found: List[Dict[str, str]] = []
    seen: Set[str] = set()
    if not text:
        return found
    for match in _HONORIFIC_NAME_RE.finditer(text):
        name = _trim_company_words(_clean_name(match.group(1)), company_name)
        if not is_plausible_person_name(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append({"name": name, "title": "", "role_unknown": "true"})
    return found


def _walk_jsonld(node: Any, out: List[Dict[str, str]], depth: int = 0) -> None:
    """Walks a JSON-LD tree collecting people with a job title."""
    if depth > 8:
        return
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, out, depth + 1)
        return
    if not isinstance(node, dict):
        return

    def _add(raw_name: Any, raw_title: Any) -> None:
        if not isinstance(raw_name, str) or not isinstance(raw_title, str):
            return
        clean = _clean_name(raw_name)
        if not is_plausible_person_name(clean):
            return
        title = _canonical_title(raw_title)
        if not title:
            return
        # The same person is reachable twice - once through the
        # Organization's "employee" array and once by recursing into that
        # entry - so de-duplicate here rather than emitting them twice.
        if any(e["name"].lower() == clean.lower() for e in out):
            return
        out.append({"name": clean, "title": title})

    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    types = [str(t).lower() for t in types if t]

    if "person" in types:
        _add(
            node.get("name"),
            node.get("jobTitle") or node.get("title") or node.get("role"),
        )

    # Organization -> employee / founder / member
    for key in ("employee", "founder", "member", "employees", "founders",
                "staff", "people"):
        value = node.get(key)
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                _add(
                    item.get("name"),
                    item.get("jobTitle") or item.get("title") or item.get("role"),
                )

    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk_jsonld(value, out, depth + 1)


def extract_executives_from_jsonld(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Reads ``application/ld+json`` blocks for people and their roles."""
    out: List[Dict[str, str]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # Some sites emit JSON-LD with trailing commas or HTML comments.
            cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
            cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                data = json.loads(cleaned)
            except Exception:
                continue
        _walk_jsonld(data, out)
    return out


def merge_executives(
    *groups: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Merges several extraction passes, keeping the first title for a name.

    JSON-LD comes first, so a structured ``jobTitle`` wins over a
    regex-guessed one. A name found without a role does not overwrite a
    name that was found with one.
    """
    merged: List[Dict[str, str]] = []
    index: Dict[str, int] = {}
    for group in groups:
        for item in group or []:
            name = (item.get("name") or "").strip()
            title = (item.get("title") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in index:
                # A role-less sighting does not downgrade a known role.
                if not title and merged[index[key]].get("title"):
                    continue
                if title and merged[index[key]].get("title"):
                    continue
                continue
            index[key] = len(merged)
            merged.append({
                "name": name,
                "title": title,
                **({"role_unknown": "true"} if not title else {}),
            })
    return merged


def bind_executives_to_email(
    email: str,
    executives: List[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """Binds an email address to the executive it plausibly belongs to.

    A shared mailbox (``info@``) belongs to nobody. A person address
    carries their name - or their initials - in the local part. When the
    address is a guess built from the executive's own name, it always
    matches.
    """
    if not email or "@" not in email or not executives:
        return None
    local = email.split("@")[0].lower().strip()
    if not local:
        return None

    tokens = [t for t in re.split(r"[._+\-]", local) if t]
    if not tokens:
        return None

    for ex in executives:
        parts = (ex.get("name") or "").lower().split()
        if not parts:
            continue
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        if first and first in tokens:
            return ex
        if last and last in tokens:
            return ex
        # Initials: "rsharma" for Rajesh Sharma.
        if first and last and len(first) == 1 and tokens[0] == first:
            return ex
        # Full name squashed together: "rajeshsharma".
        joined = "".join(parts)
        if len(joined) > 5 and joined in re.sub(r"[^a-z]", "", local):
            return ex
    return None
