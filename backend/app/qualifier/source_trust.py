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
be great, it just needs a phone re-check first. Pure function, unit-testable.
"""

from typing import Any, Dict, Optional

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


def source_trust(source: Optional[str]) -> tuple:
    """``(trust, note)`` for a Business.source value. Unknown -> default."""
    if not source:
        return DEFAULT_TRUST, DEFAULT_NOTE
    return SOURCE_TRUST.get(str(source).strip().lower(), (DEFAULT_TRUST, DEFAULT_NOTE))


def trust_score_modifier(trust: float) -> float:
    """Maps trust [0,1] to a bounded score modifier in [-8, +5].

    A pristine first-party source nudges the score up; a shared/stale
    directory lead is discounted but never zeroed — the phone check is the
    operator's call, not ours.
    """
    trust = max(0.0, min(1.0, float(trust)))
    return round(-8.0 + 13.0 * trust, 2)


def annotate_lead(business: Any) -> Dict[str, Any]:
    """Adds ``source_trust`` / ``source_note`` / ``trust_modifier`` to a lead dict."""
    source = business.get("source") if isinstance(business, dict) else getattr(business, "source", None)
    trust, note = source_trust(source)
    out = {
        "source": source,
        "source_trust": trust,
        "source_note": note,
        "trust_modifier": trust_score_modifier(trust),
    }
    if isinstance(business, dict):
        out.update(business)
    return out
