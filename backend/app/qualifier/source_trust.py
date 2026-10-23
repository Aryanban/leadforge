"""Source-trust weighting for India lead lists.

Buyer beware is the loudest JustDial/IndiaMART complaint on Reddit/Quora:
shared leads, fake/disconnected numbers, decade-old self-listed data. Reddit
also says plainly "never trust a vendor's sample data — run your own list
and count what comes back."

LeadForge can't scrub anyone else's data, but it *can* rank what it scraped:

* Live-Google sources (Maps) refresh themselves because businesses depend on
  their GBP for search traffic — highest freshness.
* Self-listed directories (JustDial/IndiaMART/Sulekha) rely on businesses to
  self-update — stale data and shared leads are common, so their leads carry
  a documented trust discount.
* Website-harvested contacts (crawled from the business's own site) are
  effectively first-party and rank with Maps.

Trust feeds a score *modifier* (not a gate): a stale-directory lead can still
be great, it just needs a phone re-check first. The calibration formula is
pure and unit-testable; database outcome loading is separate.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, case, func, or_, select

#: Source key -> (trust 0-1, one-line rationale shown in the dashboard).
#:
#: The keys must cover every source the scrapers actually write. The table
#: used to omit ``playwright_maps`` / ``playwright_single`` / ``http_fallback``
#: / ``google_maps_seed`` - which are precisely the values the primary scrape
#: path stores - so the trust modifier was skipped for every lead the
#: dashboard produced, and the API still advertised a trust badge next to a
#: score that had never included it.
SOURCE_TRUST: Dict[str, tuple] = {
    "google_maps": (0.95, "Live GBP data; businesses keep it current."),
    "maps": (0.95, "Live GBP data; businesses keep it current."),
    "google_maps_scraper": (0.95, "Live GBP data; businesses keep it current."),
    # Values written by the live scrape paths.
    "google_maps_http": (0.95, "Live GBP data; businesses keep it current."),
    "playwright_maps": (0.95, "Live GBP data; businesses keep it current."),
    "playwright_single": (0.95, "Live GBP data; businesses keep it current."),
    "http_fallback": (0.85, "Web-search fallback; freshness varies."),
    "google_maps_seed": (0.95, "Live GBP data; businesses keep it current."),
    "website": (0.90, "First-party: crawled from the business's own site."),
    "website_scrape": (0.90, "First-party: crawled from the business's own site."),
    "web_search": (0.75, "Found via web search; verify before a full sequence."),
    "pattern_guess": (0.55, "Guessed from the domain's email pattern; not yet confirmed."),
    "alias": (0.80, "Department mailbox (info@/sales@); not a named person."),
    "multi_source_enricher": (0.85, "Merged from site crawl + web search."),
    "indiamart": (0.60, "Self-listed B2B directory; verify the phone first."),
    "justdial": (0.50, "Self-listed; shared leads and stale numbers are common."),
    "sulekha": (0.50, "Self-listed; leads may be resold to competitors."),
    "in_phone": (0.65, "Directory aggregator; numbers are often stale."),
    "discovery": (0.70, "Directory fan-out; freshness varies by source."),
    "csv_import": (0.75, "Your own list — quality depends on provenance."),
}

DEFAULT_TRUST = 0.70
DEFAULT_NOTE = "Unrated source; verify the phone before a full sequence."
TRUST_PRIOR_STRENGTH = 20.0


def source_trust(source: Optional[str]) -> tuple:
    """``(trust, note)`` for a Business.source value. Unknown -> default."""
    if not source:
        return DEFAULT_TRUST, DEFAULT_NOTE
    return SOURCE_TRUST.get(str(source).strip().lower(), (DEFAULT_TRUST, DEFAULT_NOTE))


def calibrate_source_trust(
    source: Optional[str], outcomes: Optional[Dict[str, int]] = None
) -> float:
    """Blend the documented source prior with recent verification and send results.

    A source prior is worth 20 observations. Recent email verification samples
    add one observation each; actual SMTP acceptances/hard bounces add two,
    capped at 50 per signal so one large list cannot erase the prior overnight.
    The caller supplies a bounded time window, so this can adapt as source
    quality changes without storing stale lifetime rates.
    """
    prior, _ = source_trust(source)
    outcomes = outcomes or {}
    checked = max(0, int(outcomes.get("email_checks", 0) or 0))
    verified = max(0, min(checked, int(outcomes.get("verified_emails", 0) or 0)))
    sends = max(0, int(outcomes.get("send_outcomes", 0) or 0))
    bounced = max(0, min(sends, int(outcomes.get("hard_bounces", 0) or 0)))

    weight = TRUST_PRIOR_STRENGTH
    quality_total = prior * TRUST_PRIOR_STRENGTH
    if checked:
        sample_weight = min(float(checked), 50.0)
        quality_total += (verified / checked) * sample_weight
        weight += sample_weight
    if sends:
        sample_weight = min(float(sends), 50.0) * 2.0
        quality_total += ((sends - bounced) / sends) * sample_weight
        weight += sample_weight
    return round(max(0.0, min(1.0, quality_total / weight)), 4)


async def source_outcomes_by_source(
    db: Any, window_days: int = 90
) -> Dict[str, Dict[str, int]]:
    """Aggregate recent, attributable quality outcomes by discovery source.

    Verification outcomes are counted from the latest check per contact. SMTP
    outcomes use completed sends and hard bounces only; transient failures are
    excluded because they say more about the sender than about the lead.
    """
    from app.models.business import Business
    from app.models.contact import Contact
    from app.models.send import Send

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))
    outcomes: Dict[str, Dict[str, int]] = {}

    verification_rows = await db.execute(
        select(
            Business.source,
            func.count(Contact.id),
            func.sum(case((Contact.is_verified.is_(True), 1), else_=0)),
        )
        .join(Contact, Contact.business_id == Business.id)
        .where(
            Business.source.isnot(None),
            Contact.verification_checked_at >= cutoff,
            Contact.verification_status != "bounced",
        )
        .group_by(Business.source)
    )
    for source, checked, verified in verification_rows:
        key = str(source).strip().lower()
        outcomes[key] = {
            "email_checks": int(checked or 0),
            "verified_emails": int(verified or 0),
            "send_outcomes": 0,
            "hard_bounces": 0,
        }

    send_rows = await db.execute(
        select(
            Business.source,
            func.count(Send.id),
            func.sum(case((Send.bounced.is_(True), 1), else_=0)),
        )
        .join(Contact, Send.contact_id == Contact.id)
        .join(Business, Contact.business_id == Business.id)
        .where(
            Business.source.isnot(None),
            or_(
                Send.sent_at >= cutoff,
                and_(Send.sent_at.is_(None), Send.created_at >= cutoff),
            ),
            or_(
                Send.status == "sent",
                and_(Send.status == "bounced", Send.bounced.is_(True)),
            ),
        )
        .group_by(Business.source)
    )
    for source, sends, bounced in send_rows:
        key = str(source).strip().lower()
        row = outcomes.setdefault(key, {
            "email_checks": 0,
            "verified_emails": 0,
            "send_outcomes": 0,
            "hard_bounces": 0,
        })
        row["send_outcomes"] = int(sends or 0)
        row["hard_bounces"] = int(bounced or 0)
    return outcomes


async def source_trust_overrides(db: Any, window_days: int = 90) -> Dict[str, float]:
    """Return learned source trust values where recent evidence exists."""
    outcomes = await source_outcomes_by_source(db, window_days=window_days)
    return {
        source: calibrate_source_trust(source, samples)
        for source, samples in outcomes.items()
    }


def trust_score_modifier(trust: float) -> float:
    """Maps trust [0,1] to a bounded score modifier in [-8, +5].

    A pristine first-party source nudges the score up; a shared/stale
    directory lead is discounted but never zeroed — the phone check is the
    operator's call, not ours.
    """
    trust = max(0.0, min(1.0, float(trust)))
    return round(-8.0 + 13.0 * trust, 2)


def annotate_lead(
    business: Any,
    learned_trust: Optional[float] = None,
    outcomes: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Adds ``source_trust`` / ``source_note`` / ``trust_modifier`` to a lead dict."""
    source = business.get("source") if isinstance(business, dict) else getattr(business, "source", None)
    trust, note = source_trust(source)
    if learned_trust is not None:
        trust = max(0.0, min(1.0, float(learned_trust)))
        sample_count = (
            (outcomes or {}).get("email_checks", 0)
            + (outcomes or {}).get("send_outcomes", 0)
        )
        note = f"{note} Calibrated from {sample_count} recent verification and send outcomes."
    out = {
        "source": source,
        "source_trust": trust,
        "source_note": note,
        "trust_modifier": trust_score_modifier(trust),
        "source_trust_samples": (
            (outcomes or {}).get("email_checks", 0)
            + (outcomes or {}).get("send_outcomes", 0)
        ),
    }
    if isinstance(business, dict):
        out.update(business)
    return out
