"""Google Maps discovery over plain HTTP - no browser, no DOM, no scrolling.

Why this exists
---------------
The Playwright path (``maps_scraper.py``) drives a real browser, queries DOM
selectors and scrolls a virtualised feed. It works, but it is the slowest and
most fragile of the available options: the feed only renders ~20 cards before
a scroll is required, and every scroll plus selector query is a round-trip
through the browser runtime.

Google exposes the same data as a JSON blob on
``/search?tbm=map&...&pb=<protobuf-ish string>``. One request returns 20
results *with name, phone, website, address, rating, review count and
lat/lng* in roughly 0.3-0.9 s. This makes 100-200 leads for a query cost a
handful of HTTP calls and well under a second of wall-clock, instead of tens
of seconds of browser driving.

The array indices below are Google-internal and can change without notice.
They are mirrored from a widely-deployed production scraper (gosom/
google-maps-scraper) and are wrapped in defensive accessors, so a shifted
index degrades to a missing field rather than an exception. When Google
reshuffles them, only the ``_IDX_*`` constants and the readers need touching -
the request/response plumbing stays valid.

Compliance note: this is an undocumented endpoint and is not covered by the
Maps Platform ToS. It is therefore opt-in (``GOOGLE_MAPS_HTTP_FALLBACK``).
For high-volume or commercial use, switch to the official Places API (New);
the parse step here is structured so that swap is a change of transport only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.scraper.maps_scraper import industry_of_query

logger = logging.getLogger(__name__)

# A desktop-Chrome UA is enough for this endpoint; it does not need the full
# anti-detection stack the browser path requires.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_ENDPOINT = "https://maps.google.com/search"

# The XSSI guard Google prepends to JSON responses.
_XSSI_PREFIXES = (")]}'", ")]}'", ")]}'\n")

#: pb= takes a lat/lng viewport centre, not a place name, so a query needs one
#: geocode. Nominatim (OSM) is free and needs no key - one lookup per query,
#: never per lead.
_NOMINATIM = "https://nominatim.openstreetmap.org/search"

# --- Response indices -------------------------------------------------------
# Paths into the nested arrays of one result. Named constants because they are
# the part most likely to break, and bare [178] everywhere is how these files
# become unmaintainable.
_IDX_NAME = (11,)
_IDX_CATEGORIES = (13,)
_IDX_WEBSITE = (7, 0)
_IDX_RATING = (4, 7)
_IDX_REVIEWS = (4, 8)
_IDX_ADDRESS = (2,)      # list of address lines (fallback)
_IDX_ADDRESS_FULL = (18,)  # complete formatted address string (preferred)
_IDX_REVIEWS_LABEL = (4, 3, 1)  # e.g. "1,870 reviews" - count embedded in prose
_IDX_LAT = (9, 2)
_IDX_LNG = (9, 3)
_IDX_PHONE = (178, 0, 0)
_IDX_STATUS = (88, 0)  # "CLOSED_PERMANENTLY" / "CLOSED_TEMPORARILY" / None
_IDX_TIMEZONE = (30,)
_IDX_DATA_ID = (10,)
_IDX_ENTRY = (14,)

#: Results per request. Fixed by Google, not by us.
_PAGE_SIZE = 20


def _strip_xssi(raw: str) -> str:
    for prefix in _XSSI_PREFIXES:
        if raw.startswith(prefix):
            return raw[len(prefix):].lstrip("\n")
    return raw


def _dig(payload: Any, path: Tuple[int, ...]) -> Any:
    """Walks a nested-list path, returning None on any miss.

    The response is positional JSON: a missing field is normally a *shorter*
    array rather than an explicit null, so every hop needs a length check.
    """
    node = payload
    for key in path:
        if isinstance(node, (list, tuple)) and len(node) > key:
            node = node[key]
        else:
            return None
    return node


def _dig_str(payload: Any, path: Tuple[int, ...]) -> Optional[str]:
    value = _dig(payload, path)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _dig_float(payload: Any, path: Tuple[int, ...]) -> Optional[float]:
    value = _dig(payload, path)
    # bool is an int subclass; a rating is never True/False.
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _dig_int(payload: Any, path: Tuple[int, ...]) -> Optional[int]:
    value = _dig_float(payload, path)
    return int(value) if value is not None else None


def _dig_reviews(raw: Any) -> Optional[int]:
    """Resolves the review count, which arrives in two shapes.

    Normally it is the integer at ``(4, 8)``. On some responses Google instead
    ships a reviews *link* at ``(4, 3)`` whose label is the count as prose
    ("1,870 reviews"), with the integer slot absent - so parse the digits out
    of the label rather than losing the count entirely.
    """
    count = _dig_int(raw, _IDX_REVIEWS)
    if count is not None:
        return count

    label = _dig_str(raw, _IDX_REVIEWS_LABEL)
    if label:
        digits = re.sub(r"[^0-9]", "", label)
        if digits:
            return int(digits)
    return None


def _dig_phone(raw: Any) -> Optional[str]:
    """Resolves the phone number, preferring the international form.

    Google stores a phone as a small structure::

        [ "075593 56392",                       # display form (leading 0)
          [ ["075593 56392", 1],                #   type 1 = as displayed
            ["+91 75593 56392", 2] ],          #   type 2 = international
          null,
          "07559356392",                       # compact local
          null,
          ["tel:07559356392", ...] ]

    The old code took the *display* form, which for India carries a
    leading trunk zero ("075593 56392"). That is the wrong shape for an
    Indian mobile: it looks like a landline with STD code 075593, so the
    STD->city resolver mis-files it and the number does not match a
    "+91 75593 56392" stored elsewhere for the same business.

    The international form is unambiguous, so it wins when present.
    """
    # ``_IDX_PHONE`` is (178, 0, 0) - the trailing 0 lands on the display
    # string. We want the *enclosing* structure, so dig one level less.
    node = _dig(raw, _IDX_PHONE[:-1])
    if not isinstance(node, (list, tuple)) or not node:
        return _dig_str(raw, _IDX_PHONE)

    # Depending on the response, ``node`` is either the entry itself or a
    # one-element list wrapping it.
    entry = node
    if isinstance(node[0], (list, tuple)) and node[0] and not isinstance(node[0], str):
        entry = node[0]
    if not isinstance(entry, (list, tuple)) or not entry:
        return _dig_str(raw, _IDX_PHONE)

    # entry[1] is the list of [number, type] pairs.
    variants = entry[1] if len(entry) > 1 else None
    if isinstance(variants, (list, tuple)):
        international = None
        display = None
        for variant in variants:
            if not (isinstance(variant, (list, tuple)) and len(variant) >= 2):
                continue
            number, kind = variant[0], variant[1]
            if not isinstance(number, str) or not number.strip():
                continue
            if kind == 2 and international is None:
                international = number.strip()
            elif display is None:
                display = number.strip()
        if international:
            return international
        if display:
            return display

    # Fall back to the display field at entry[0].
    if isinstance(entry[0], str) and entry[0].strip():
        return entry[0].strip()
    return _dig_str(raw, _IDX_PHONE)


def _dig_address(raw: Any, name: Optional[str] = None) -> Optional[str]:
    """Resolves the address, which Google stores in two shapes.

    Index 2 carries a list of address *lines* (building, street, locality,
    city, PIN) and is the cleaner source. Index 18 carries one pre-joined
    string, but it interpolates the business's SEO title into the front of it,
    so it is only a fallback. A street-level address is what an India lead
    needs - the city and PIN drive ICP matching and the STD-code lookup.
    """
    parts = _dig(raw, _IDX_ADDRESS)
    if isinstance(parts, (list, tuple)):
        lines = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        # Google sometimes prefixes the first line with the SEO title, which is
        # already captured as the name; drop it so the address stays an address.
        if lines and name and lines[0].lower().startswith(name.lower()[:20]):
            lines = lines[1:]
        if lines:
            return ", ".join(lines)

    return _dig_str(raw, _IDX_ADDRESS_FULL)


# --- The pb= parameter ------------------------------------------------------
# The bulk of this string is opaque to us: Google encodes the viewport, the
# requested feature flags and experiment ids in it. The two placeholders that
# matter are the viewport centre ({lat}/{lng}) and, on later pages, the
# continuation token. The rest is preserved verbatim because Google rejects a
# pb= with a different shape.
_PB_TEMPLATE = (
    "!4m12!1m3!1d3826.902183192154!2d{lng}!3d{lat}"
    "!2m3!1f0!2f0!3f0"
    "!3m2!1i600!2i800!4f{zoom}.0!7i20!8i0"
    "!10b1!12m22!1m3!18b1!30b1!34e1!2m3!5m1!6e2!20e3!4b0!10b1!12b1!13b1"
    "!16b1!17m1!3e1!20m3!5e2!6b1!14b1!46m1!1b0!96b1"
    "!19m4!2m3!1i360!2i120!4i8"
)

#: Zoom controls the search radius around the viewport centre. 12 is roughly a
#: city-neighbourhood spread, which is what a "dentists in Rohini" query wants.
_DEFAULT_ZOOM = 12


def build_pb(lat: float, lng: float, page_token: Optional[str] = None,
             zoom: int = _DEFAULT_ZOOM) -> str:
    """Builds the ``pb`` value for one Maps search request."""
    pb = _PB_TEMPLATE.format(lat=lat, lng=lng, zoom=zoom)
    if page_token:
        pb += f"!{page_token}"
    return pb


# --- Geocoding --------------------------------------------------------------
async def _geocode(query: str, timeout: float = 10.0) -> Optional[Tuple[float, float]]:
    """Resolves the location part of a query to a lat/lng via OSM Nominatim.

    One lookup per query, never per lead. Returns None on any failure so the
    caller can skip the HTTP path rather than guess a viewport.

    The result is pinned to India. Without ``countrycodes`` a locality like
    "Whitefield" resolves to Whitefield, **New Hampshire** and "Park Street" to
    Park Street, **Boston** - and because this geocode is the only geographic
    scope of the entire scrape, that silently put US businesses into an
    India-targeted database. The ``country_code`` guard below is a hard
    backstop in case the parameter is ignored.
    """
    headers = {
        "User-Agent": "LeadForge/1.0 (+https://github.com/Aryanban/leadforge)",
        "Accept-Language": "en",
    }
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.get(_NOMINATIM, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
    except Exception as exc:  # network down, rate limited, malformed JSON
        logger.debug("Nominatim lookup failed for %r: %s", query, exc)
        return None

    if not isinstance(data, list) or not data:
        return None
    try:
        country = str(data[0].get("country_code", "")).lower()
        if country and country != "in":
            logger.warning(
                "geocode for %r resolved outside India (%s) - skipping", query, country
            )
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _location_of_query(query: str) -> str:
    """Pulls the location clause out of a Maps query, for geocoding.

    "dentists in Rohini Delhi" -> "Rohini Delhi". A bare query is used as-is.
    """
    from app.scraper.maps_scraper import _QUERY_SPLIT_RE

    parts = _QUERY_SPLIT_RE.split(query.strip(), maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else query.strip()


# --- Request / parse --------------------------------------------------------
async def _fetch_page(query: str, lat: float, lng: float,
                      page_token: Optional[str] = None,
                      client: Optional[httpx.AsyncClient] = None,
                      zoom: int = _DEFAULT_ZOOM,
                      search_term: Optional[str] = None) -> Optional[Any]:
    """Fetches one page of Maps results and returns the parsed envelope.

    ``search_term`` is what we ask Google for. It defaults to ``query`` but
    should be the *category only* ("dentists"), never "dentists in Delhi" -
    see ``scrape_google_maps_http``.
    """
    params = {
        "tbm": "map",
        "hl": "en",
        "gl": "in",          # biases results to India
        "q": search_term or query,
        "pb": build_pb(lat, lng, page_token, zoom),
    }
    headers = {
        "User-Agent": getattr(settings, "SCRAPER_USER_AGENT", None) or _DEFAULT_UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        # httpx sends no Accept-Encoding by default, so every response comes
        # back uncompressed - a strong bot signal and a lot of wasted bytes.
        "Accept-Encoding": "gzip, deflate",
        "Referer": "https://www.google.com/maps/",
    }

    async def _do(c: httpx.AsyncClient, attempt: int = 0) -> Optional[Any]:
        try:
            resp = await c.get(_ENDPOINT, params=params, headers=headers)
        except Exception as exc:
            if attempt < 2:
                delay = (2 ** attempt) * 1.5 + random.uniform(0, 0.8)
                logger.debug("Maps request error (%s), retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
                return await _do(c, attempt + 1)
            logger.debug("Maps request failed for %r: %s", query, exc)
            return None

        if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            # A throttled cell silently contributed nothing before, which cost
            # a third of the results on a bad run. Back off and retry.
            delay = (2 ** attempt) * 2.0 + random.uniform(0, 1.0)
            logger.info("Maps returned %s, retrying in %.1fs", resp.status_code, delay)
            await asyncio.sleep(delay)
            return await _do(c, attempt + 1)

        if resp.status_code != 200:
            logger.debug("Maps pb= returned %s for %r", resp.status_code, query)
            return None
        try:
            return json.loads(_strip_xssi(resp.text))
        except json.JSONDecodeError as exc:
            logger.debug("Maps pb= unparseable body for %r: %s", query, exc)
            return None

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as c:
        return await _do(c)


def _viewport_grid(lat: float, lng: float, max_cells: int,
                   spacing_km: float = 3.5) -> List[Tuple[float, float]]:
    """Turns a centre point into a ring-and-square grid of viewport centres.

    Google ranks ~20 results per request against the viewport, so neighbouring
    viewports mostly return *different* businesses - that is the only way past
    the 20-result ceiling on this endpoint. The first cell is always the
    centre itself (highest relevance), then a ring, then an outer square.

    ``max_cells`` is rounded up to a square so the grid stays symmetrical.

    The true centre is emitted exactly once. The grid used to add the centre
    explicitly *and* emit it again from the loop, so a 8-cell grid made only
    7 distinct HTTP requests - one of them a 100% duplicate of the centre.
    """
    if max_cells <= 1:
        return [(lat, lng)]

    side = max(1, int(math.ceil(math.sqrt(max_cells))))
    # 1 degree of latitude is ~111 km. Longitude degrees shrink with latitude.
    d_lat = spacing_km / 111.0
    d_lng = spacing_km / (111.0 * max(math.cos(math.radians(lat)), 1e-6) or 1.0)

    cells: List[Tuple[float, float]] = [(lat, lng)]
    offset = (side - 1) / 2.0
    centre_i = centre_j = offset
    for i in range(side):
        for j in range(side):
            if i == j == 0:
                continue
            if float(i) == centre_i and float(j) == centre_j:
                # Already emitted as the first cell.
                continue
            cells.append((lat + (i - offset) * d_lat, lng + (j - offset) * d_lng))
            if len(cells) >= max_cells:
                return cells
    return cells


def _extract_results(envelope: Any) -> List[Any]:
    """Returns the list of raw place arrays from a response envelope.

    Verified shape: ``envelope[0][1]`` is the result block, where element 0 is
    a header and elements 1..n are ``[..., place_array, ...]`` rows whose
    business payload lives at index 14. The positional probe comes first and a
    structural scan follows, so a shift at the envelope level degrades to fewer
    results rather than an exception.
    """
    if not isinstance(envelope, list) or not envelope:
        return []

    block = _dig(envelope, (0, 1))
    if isinstance(block, list):
        rows = [
            place for place in
            (_dig(row, _IDX_ENTRY) for row in block if isinstance(row, list))
            if isinstance(place, list) and _dig_str(place, _IDX_NAME)
        ]
        if rows:
            return rows

    # Fallback: walk the envelope looking for any row that carries a name at
    # the documented index. Catches the case where Google inserts a wrapper.
    found: List[Any] = []
    for node in envelope:
        if not isinstance(node, list):
            continue
        for row in node:
            if not isinstance(row, list):
                continue
            place = _dig(row, _IDX_ENTRY)
            if isinstance(place, list) and _dig_str(place, _IDX_NAME):
                found.append(place)
    return found


def _extract_page_token(envelope: Any) -> Optional[str]:
    """Finds the continuation token for the next page, if Google offered one.

    The token is a base64 blob embedded in the ``pb`` grammar of the *next*
    request, so it is returned as a bare suffix (``!20e3!64s...`` style).
    """
    token = _dig(envelope, (0, 1, 64))
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def parse_place(raw: List[Any], query: str) -> Optional[Dict[str, Any]]:
    """Maps one raw place array onto the scraper's result dict.

    A record without a name is not a lead, so those are dropped.
    """
    name = _dig_str(raw, _IDX_NAME)
    if not name:
        return None

    data_id = _dig_str(raw, _IDX_DATA_ID)

    # Index 13 holds a list of category groups; the primary one comes first.
    categories = _dig(raw, _IDX_CATEGORIES)
    if isinstance(categories, list) and categories and isinstance(categories[0], list):
        categories = categories[0]
    categories = categories if isinstance(categories, list) else None

    website = _dig_str(raw, _IDX_WEBSITE)
    if website and not website.startswith("http"):
        website = f"https://{website}"

    # Present only for closed businesses; "CLOSED_PERMANENTLY" /
    # "CLOSED_TEMPORARILY". Worth capturing - a closed clinic is not a lead.
    status = _dig_str(raw, _IDX_STATUS)
    address = _dig_address(raw, name)

    return {
        "name": name,
        "phone": _dig_phone(raw),
        "website": website,
        # Downstream uses the address as a location hint; losing it loses the
        # city for the whole lead, so fall back to the queried area.
        "address": address or _location_of_query(query),
        "rating": _dig_float(raw, _IDX_RATING),
        "reviews_count": _dig_reviews(raw),
        "industry": industry_of_query(query),
        "source": "google_maps_http",
        "query": query,
        "timezone": _dig_str(raw, _IDX_TIMEZONE),
        "categories": categories,
        "google_data_id": data_id,
        "maps_url": f"https://www.google.com/maps/place/?q=place_id:{data_id}" if data_id else None,
        "is_closed": bool(status),
        "closed_note": status,
        "latitude": _dig_float(raw, _IDX_LAT),
        "longitude": _dig_float(raw, _IDX_LNG),
    }


async def scrape_google_maps_http(query: str, max_results: int = 60,
                                  max_cells: int = 0,
                                  zoom: int = _DEFAULT_ZOOM,
                                  search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """Scrapes Google Maps over plain HTTP, sweeping a grid of viewports.

    Google returns at most 20 results per request and, on this endpoint, offers
    no pagination token. The way past that ceiling is to *narrow the viewport*:
    the same query centred a couple of kilometres away returns a mostly
    different set of 20. So we geocode once, then fan out over a grid of
    viewport centres concurrently and dedupe on Google's CID.

    For an Indian city query this is the difference between 20 leads and 120
    for one query, at roughly the cost of one extra geocode.

    Returns the same dict shape as its Playwright counterpart, so callers need
    not care which ran.

    IMPORTANT - the text query must stay category-only
    ----------------------------------------------------
    ``query`` is the human-facing label ("dentists in Delhi") and is used for
    the industry, the address fallback and the logs. The string actually sent
    to Google is ``search_term``, which must be the **category only**
    ("dentists").

    Sending "dentists in Delhi" makes Google return one city-wide relevance
    set, so every viewport in the grid returned a near-identical top-20 and
    the sweep was wasted. Measured live on the same 8-cell grid:

        q="dentists in Delhi"  -> 160 raw rows, 30 unique leads
        q="dentists"           -> 160 raw rows, 103 unique leads

    The distance distribution proves it: with the category-only query the
    median result sits 1.3 km from its own viewport centre (p90 = 5.0 km);
    with the city in the query it sits 5.4 km away and the sets are
    identical across cells. The viewport grid only does geographic scoping
    when the text query leaves the geography to the viewport.
    """
    coords = await _geocode(_location_of_query(query))
    if not coords:
        logger.info("Could not geocode %r - skipping HTTP Maps path", query)
        return []
    lat, lng = coords

    # Default to the category part of the query.
    if search_term is None:
        search_term = industry_of_query(query)

    # Size the grid to the requested result count. Each viewport yields roughly
    # 15 unique businesses after overlap, so asking for 100 leads from 8
    # viewports threw away 60% of what we had already paid for.
    # ``max_cells=0`` means "choose for me"; an explicit value is respected.
    if max_cells <= 0:
        max_cells = max(4, min(25, int(math.ceil(max_results / 15)) or 4))

    cells = _viewport_grid(lat, lng, max_cells)
    results: List[Dict[str, Any]] = []
    seen: set = set()

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        # One cell per viewport, all in flight. A single source quota bounds how
        # many sockets we open to Google at once.
        semaphore = asyncio.Semaphore(getattr(settings, "SOURCE_MAX_CONCURRENCY", 4) or 4)

        async def _sweep(cell: Tuple[float, float]) -> List[Dict[str, Any]]:
            async with semaphore:
                envelope = await _fetch_page(
                    query, cell[0], cell[1], client=client, zoom=zoom,
                    search_term=search_term,
                )
                if envelope is None:
                    return []
                found: List[Dict[str, Any]] = []
                for raw in _extract_results(envelope)[:_PAGE_SIZE]:
                    place = parse_place(raw, query)
                    if place:
                        found.append(place)
                return found

        batches = await asyncio.gather(
            *(_sweep(cell) for cell in cells), return_exceptions=True
        )

    for batch in batches:
        if isinstance(batch, BaseException):
            logger.debug("Maps cell failed for %r: %s", query, batch)
            continue
        for place in batch:
            # Dedupe on the strongest key available: Google's CID, else
            # name+address. CIDs are what keep grid overlap from double-counting.
            key = place["google_data_id"] or (
                place["name"].lower(), place["address"].lower()
            )
            if key in seen:
                continue
            seen.add(key)
            results.append(place)
            if len(results) >= max_results:
                break

    logger.info(
        "HTTP Maps scrape for %r (q=%r) returned %d leads across %d viewports",
        query, search_term, len(results), len(cells),
    )
    return results[:max_results]


