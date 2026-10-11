"""Email pattern inference: learn how a domain builds mailboxes, then guess smart.

The old approach generated permutations from the *company name*
("Sharma Dental Clinic" -> ``sharma.dental@``), which manufactures addresses
no human would own and burns verification budget confirming they bounce.

Paid tools (Apollo/Hunter) do it the other way round: they harvest **seed**
emails already published on the domain, learn which ``{first}/{last}``
pattern the company uses, and only then generate candidates - for real
*person* names (executives found on the site), never for the company name.

Pipeline::

    seeds (harvested on domain) -> infer_pattern -> pattern + confidence
    no seeds                     -> global prior ranking (most common first)
    person names                 -> candidates in pattern order
    company name                 -> never
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Person-pattern templates, ordered by global prior (how often each pattern
#: occurs across corporate mailboxes). ``infer_pattern`` re-orders these when
#: seeds say otherwise. Each entry is ``(name, template)``.
PATTERN_PRIORS: Tuple[Tuple[str, str], ...] = (
    ("first.last", "{first}.{last}"),
    ("first", "{first}"),
    ("firstlast", "{first}{last}"),
    ("f.last", "{f}.{last}"),
    ("first_last", "{first}_{last}"),
    ("flast", "{f}{last}"),
    ("first-lastr", "{first}-{last}"),
    ("last.first", "{last}.{first}"),
    ("firstl", "{first}{l}"),
    ("last", "{last}"),
)

#: Weight of the global prior vs seed evidence when blending confidence.
#: One seed is suggestive, not conclusive; three agreeing seeds dominate.
PRIOR_WEIGHT = 2.0

#: Local parts that are shared mailboxes, not evidence of a person pattern.
_GENERIC_LOCALS = frozenset({
    "info", "contact", "contacts", "sales", "support", "hello", "admin",
    "office", "enquiry", "enquiries", "inquiry", "inquiries", "help",
    "helpdesk", "marketing", "billing", "accounts", "reception", "team",
    "service", "services", "orders", "booking", "bookings", "appointments",
    "careers", "jobs", "hr", "press", "media", "legal", "privacy",
    "noreply", "no-reply", "donotreply", "mail", "email", "general",
    "enquire", "webmaster", "postmaster", "abuse", "security",
})

_COMPANY_SUFFIXES = frozenset({
    "limited", "ltd", "private", "pvt", "llc", "inc", "corp", "corporation",
    "associates", "agency", "realty", "group", "services", "enterprises",
    "traders", "trading", "industries", "solutions", "systems", "clinic",
    "hospital", "school", "college", "india", "bharat",
})


def _split_local(local: str) -> List[str]:
    """Splits a mailbox local part on the separators companies actually use."""
    return [t for t in re.split(r"[._+\-]", local.strip().lower()) if t]


def match_pattern(local: str, first: str, last: str) -> Optional[str]:
    """Returns the pattern name if ``local`` fits ``(first, last)``, else None."""
    local = local.strip().lower()
    first = first.strip().lower()
    last = (last or "").strip().lower()
    if not local or not first:
        return None
    f, l = first[0], last[0] if last else ""

    if not last:
        return "first" if local == first else None

    candidates = {
        "first.last": f"{first}.{last}",
        "first": first,
        "firstlast": f"{first}{last}",
        "f.last": f"{f}.{last}",
        "first_last": f"{first}_{last}",
        "flast": f"{f}{last}",
        "first-lastr": f"{first}-{last}",
        "last.first": f"{last}.{first}",
        "firstl": f"{first}{l}",
        "last": last,
    }
    for name, rendered in candidates.items():
        if local == rendered:
            return name
    return None


def infer_pattern(
    seeds: List[str],
    domain: str,
    person_names: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[str, float]:
    """Infers a domain's mailbox pattern from harvested seed addresses."""
    domain = (domain or "").lower().strip()
    own = [
        s.strip().lower()
        for s in (seeds or [])
        if s and "@" in s and s.rpartition("@")[2].lower().strip() == domain
    ]
    own = [s for s in own if s.rpartition("@")[0] not in _GENERIC_LOCALS]

    priors = {name: 1.0 - (i * 0.06) for i, (name, _) in enumerate(PATTERN_PRIORS)}
    votes: Dict[str, float] = {name: 0.0 for name, _ in PATTERN_PRIORS}
    total = 0

    for seed in own:
        local = seed.rpartition("@")[0]
        matched: Optional[str] = None
        if person_names:
            hits = set()
            for first, last in person_names:
                hit = match_pattern(local, first, last or "")
                if hit:
                    hits.add(hit)
            if len(hits) == 1:
                matched = next(iter(hits))
        else:
            parts = _split_local(local)
            if len(parts) == 2 and all(p.isalpha() and len(p) >= 2 for p in parts):
                sep = "." if "." in local else ("_" if "_" in local else ("-" if "-" in local else ""))
                if len(parts[0]) == 1:
                    matched = "f.last" if sep == "." else ("flast" if not sep else None)
                elif len(parts[1]) == 1:
                    matched = "firstl" if not sep else None
                else:
                    matched = {"": None, ".": "first.last", "_": "first_last", "-": "first-lastr"}.get(sep)
            elif len(parts) == 1 and parts[0].isalpha() and len(parts[0]) >= 2:
                matched = "first"
        if matched:
            votes[matched] += 1.0
            total += 1

    if total == 0:
        return PATTERN_PRIORS[0][0], 0.25

    best = max(votes, key=lambda k: votes[k] + priors[k] * 0.15)
    confidence = (PRIOR_WEIGHT * priors[best] + votes[best]) / (PRIOR_WEIGHT + total)
    return best, round(min(0.95, confidence), 2)


def _render(template: str, first: str, last: str) -> str:
    first = first.strip().lower()
    last = (last or "").strip().lower()
    return template.format(first=first, last=last, f=first[:1], l=last[:1])


def generate_candidates(
    domain: str,
    person_names: Optional[List[Tuple[str, str]]] = None,
    seeds: Optional[List[str]] = None,
    max_person_candidates: int = 4,
) -> Tuple[List[str], str, float]:
    """Ordered candidates for one domain: persons first, aliases last."""
    domain = (domain or "").lower().replace("www.", "").strip()
    if not domain or "." not in domain:
        return [], "first.last", 0.0

    pattern, confidence = infer_pattern(list(seeds or []), domain, person_names)

    ordered_templates = [t for _, t in PATTERN_PRIORS]
    if pattern in dict(PATTERN_PRIORS):
        winner_tpl = dict(PATTERN_PRIORS)[pattern]
        ordered_templates.remove(winner_tpl)
        ordered_templates.insert(0, winner_tpl)

    candidates: List[str] = []
    person_count = 0
    for first, last in (person_names or [])[:2]:
        for tpl in ordered_templates:
            local = _render(tpl, first, last or "")
            if local.strip(".-_"):
                addr = f"{local}@{domain}"
                if addr not in candidates:
                    candidates.append(addr)
                    person_count += 1
            if person_count >= max_person_candidates:
                break
        if person_count >= max_person_candidates:
            break

    for alias in ("contact", "info", "sales", "office"):
        addr = f"{alias}@{domain}"
        if addr not in candidates:
            candidates.append(addr)
    return candidates, pattern, confidence
