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

What this module gets right (and used to get wrong)
---------------------------------------------------
* **Reverse-engineering, not shape-guessing.** "rsharma" is ``flast`` and
  "rajeshsharma" is ``firstlast``. A shape heuristic cannot tell them apart,
  and the old code classified *every* single-token seed as ``{first}`` at
  0.95 confidence - confidently wrong, which is worse than abstaining.
* **Evidence is unioned, not exclusive.** The name-based matcher and the
  shape-based matcher used to be ``if/else`` branches, so a seed belonging to
  the third exec on a team page (or a name the title regex mangled) taught
  us nothing at all.
* **Dominance-aware confidence.** One seed is suggestive, not conclusive.
  A pattern only earns high confidence when it *dominates* the seed set and
  there are enough seeds to dominate with.
* **Only valid addresses.** Half the old candidate budget was spent on
  syntactically impossible local parts ("priya.@acme.in", "rajesh.kumar
  sharma@acme.in") that burned real SMTP probes.
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
    ("f_last", "{f}_{last}"),
    ("f-last", "{f}-{last}"),
    ("first.l", "{first}.{l}"),
)

_PRIOR_BY_NAME = {name: template for name, template in PATTERN_PRIORS}

#: Weight of the global prior vs seed evidence when blending confidence.
#: One seed is suggestive, not conclusive; three agreeing seeds dominate.
PRIOR_WEIGHT = 2.0

#: A pattern needs at least this many seeds before it is called "learned".
MIN_SEEDS_FOR_CONFIDENCE = 2

#: A pattern must dominate the seed set by at least this much to be trusted.
MIN_DOMINANCE = 0.6

#: Weight of a weak vote (a seed that could only be one of several patterns).
WEAK_VOTE = 0.3

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

#: A syntactically valid local part. Anything else is not an address.
_LOCAL_RE = re.compile(r"^[A-Za-z0-9._+-]+$")


def _split_local(local: str) -> List[str]:
    """Splits a mailbox local part on the separators companies actually use."""
    return [t for t in re.split(r"[._+\-]", local.strip().lower()) if t]


def _is_valid_local(local: str) -> bool:
    """Whether a rendered local part could actually be an email address."""
    if not local or not _LOCAL_RE.match(local):
        return False
    # Leading/trailing separators are illegal in a local part and would be
    # rejected by the receiving MTA.
    if local[0] in ".-_" or local[-1] in ".-_":
        return False
    return True


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
        "f_last": f"{f}_{last}",
        "f-last": f"{f}-{last}",
        "first.l": f"{first}.{l}",
    }
    for name, rendered in candidates.items():
        if local == rendered:
            return name
    return None


def reverse_template(local: str) -> Optional[str]:
    """Infers a template from a local part alone (no name needed).

    Reverse-engineering beats shape heuristics. "rsharma" is ``flast`` and
    "rajeshsharma" is ``firstlast`` - but a shape heuristic cannot tell those
    apart, so the old code labelled all of them ``{first}`` at 0.95
    confidence.

    A single-token local part is genuinely ambiguous between ``{first}``,
    ``{first}{last}`` and ``{last}``, so this returns ``None`` rather than
    guessing. The name-based matcher resolves it when the person's name is
    known; otherwise the caller records a *weak* vote at most.
    """
    if not local:
        return None
    local = local.strip().lower()
    toks = _split_local(local)
    if len(toks) == 1:
        tok = toks[0]
        if not tok.isalpha() or len(tok) < 3:
            return None
        return None  # ambiguous - abstain rather than guess
    if len(toks) != 2 or not all(t.isalpha() for t in toks):
        return None
    a, b = toks
    sep = "." if "." in local else ("_" if "_" in local else ("-" if "-" in local else ""))
    if len(a) == 1:
        return {".": "f.last", "": "flast", "_": "f_last", "-": "f-last"}.get(sep)
    if len(b) == 1:
        return {"": "firstl", ".": "first.l"}.get(sep)
    if not sep:
        return "firstlast"
    return {".": "first.last", "_": "first_last", "-": "first-lastr"}.get(sep)


def infer_pattern(
    seeds: List[str],
    domain: str,
    person_names: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[str, float]:
    """Infers a domain's mailbox pattern from harvested seed addresses.

    ``person_names`` is every (first, last) pair known for the domain. It is
    used to *confirm* a template, not to gate it: a seed that matches no
    known name still contributes via :func:`reverse_template`.
    """
    domain = (domain or "").lower().strip()
    own = [
        s.strip().lower()
        for s in (seeds or [])
        if s and "@" in s and s.rpartition("@")[2].lower().strip() == domain
    ]
    own = [s for s in own if s.rpartition("@")[0] not in _GENERIC_LOCALS]

    priors = {name: 1.0 - (i * 0.06) for i, (name, _) in enumerate(PATTERN_PRIORS)}
    votes: Dict[str, float] = {name: 0.0 for name, _ in PATTERN_PRIORS}
    total = 0.0
    seed_count = 0

    for seed in own:
        local = seed.rpartition("@")[0]
        matched: Optional[str] = None
        weight = 1.0

        # 1) Name-based confirmation - the strongest evidence.
        if person_names:
            hits = set()
            for first, last in person_names:
                hit = match_pattern(local, first, last or "")
                if hit:
                    hits.add(hit)
            if len(hits) == 1:
                matched = next(iter(hits))
            elif len(hits) > 1:
                # Ambiguous between templates for this name - do not vote.
                matched = None

        # 2) Shape-based reverse engineering - used when the name did not
        #    resolve. Previously this branch only ran when there were NO
        #    person names at all, so every seed was discarded whenever the
        #    exec list was incomplete.
        if matched is None:
            matched = reverse_template(local)

        # 3) Last resort: a single alpha token might be a first name.
        if matched is None:
            toks = _split_local(local)
            if len(toks) == 1 and toks[0].isalpha() and len(toks[0]) >= 3:
                matched = "first"
                weight = WEAK_VOTE

        if matched:
            votes[matched] = votes.get(matched, 0.0) + weight
            total += weight
            seed_count += 1

    if total <= 0:
        # No usable evidence: fall back to the global prior, and be honest
        # about how little we know.
        return PATTERN_PRIORS[0][0], 0.25

    best = max(votes, key=lambda k: votes[k] + priors.get(k, 0.5) * 0.15)
    ratio = votes[best] / total
    seed_factor = min(1.0, seed_count / 3.0)
    prior = priors.get(best, 0.5)

    confidence = 0.50 * ratio + 0.30 * seed_factor + 0.20 * prior
    # One seed is never enough to be confident - a single ambiguous seed must
    # not override what most domains actually do.
    if seed_count < MIN_SEEDS_FOR_CONFIDENCE or ratio < MIN_DOMINANCE:
        confidence = min(confidence, 0.5)

    return best, round(max(0.0, min(0.99, confidence)), 2)


def _render(template: str, first: str, last: str) -> str:
    """Renders a template into a local part.

    Multi-token names are reduced to their meaningful parts: the surname is
    the *last* token ("Kumar Sharma" -> "Sharma") and the given name is the
    first token. Rendering the full multi-word string produced local parts
    containing spaces, which are not addresses at all.
    """
    first = (first or "").strip().lower()
    last = (last or "").strip().lower()
    if " " in first:
        first = first.split()[0]
    if " " in last:
        last = last.split()[-1]
    return template.format(first=first, last=last, f=first[:1], l=last[:1])


def generate_candidates(
    domain: str,
    person_names: Optional[List[Tuple[str, str]]] = None,
    seeds: Optional[List[str]] = None,
    max_person_candidates: int = 4,
) -> Tuple[List[str], str, float]:
    """Ordered candidates for one domain: persons first, aliases last.

    The person budget is spread across the people we know rather than spent
    entirely on the first one. Previously the first name consumed all four
    slots and the second person - whom we had also learned the pattern from -
    never got a single candidate.
    """
    domain = (domain or "").lower().replace("www.", "").strip()
    if not domain or "." not in domain:
        return [], "first.last", 0.0

    pattern, confidence = infer_pattern(list(seeds or []), domain, person_names)

    ordered_templates = [t for _, t in PATTERN_PRIORS]
    if pattern in _PRIOR_BY_NAME:
        winner_tpl = _PRIOR_BY_NAME[pattern]
        ordered_templates.remove(winner_tpl)
        ordered_templates.insert(0, winner_tpl)

    candidates: List[str] = []
    names = list(person_names or [])[:3]

    # Templates that need a surname are useless for a single-name contact.
    def _usable(template: str, first: str, last: str) -> bool:
        if "{last}" in template and not last:
            return False
        if "{l}" in template and not last:
            return False
        return True

    per_name = (max(1, max_person_candidates // len(names))) if names else 0
    person_count = 0

    for first, last in names:
        made = 0
        for tpl in ordered_templates:
            if not _usable(tpl, first, last):
                continue
            local = _render(tpl, first, last or "")
            if not _is_valid_local(local):
                continue
            addr = f"{local}@{domain}"
            if addr in candidates:
                continue
            candidates.append(addr)
            made += 1
            if made >= per_name or person_count + made >= max_person_candidates:
                break
        person_count += made
        if person_count >= max_person_candidates:
            break

    for alias in ("contact", "info", "sales", "office"):
        addr = f"{alias}@{domain}"
        if addr not in candidates:
            candidates.append(addr)
    return candidates, pattern, confidence
