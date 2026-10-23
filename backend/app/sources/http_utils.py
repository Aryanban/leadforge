import asyncio
import inspect
import logging
import random
import re
from typing import Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# A single static UA is the easiest fingerprint to block on, and Indian
# directories (JustDial in particular) serve a stub to anyone who looks like a
# bot. Rotating over real, current browser strings makes one bad guess cost one
# request instead of a whole source.
USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Mobile matters in India: most directory traffic is mobile, so a mobile UA
    # is not just tolerated, it often gets the *better* server-rendered page.
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
)

#: Hosts that serve an interstitial / captcha instead of content. Seeing one of
#: these means "retry with a different UA" (or give up and use a proxy), not
#: "this page has no listings".
BLOCK_MARKERS: Tuple[str, ...] = (
    "cf-browser-verification",
    "cf_chl_opt",
    "just a moment",
    "checking if the site connection is secure",
    "attention required! | cloudflare",
    "__cf_chl",
    "captcha",
    "are you a robot",
    "unusual traffic",
    "enable javascript and cookies to continue",
)

INDIAN_CITIES = (
    "delhi", "new delhi", "mumbai", "bangalore", "bengaluru", "chennai", "kolkata",
    "hyderabad", "pune", "jaipur", "lucknow", "ahmedabad", "surat", "kanpur",
    "nagpur", "indore", "patna", "bhopal", "ludhiana", "agra", "varanasi",
    "chandigarh", "coimbatore", "kochi", "madurai", "nashik", "vadodara",
    "faridabad", "ghaziabad", "noida", "greater noida", "gurgaon", "gurugram",
)

CITY_ALIASES = {
    "delhi ncr": "delhi",
    "new delhi": "delhi",
    "ncr": "delhi",
    "bengaluru": "bangalore",
    "gurugram": "gurgaon",
    "greater noida": "noida",
}


def _proxy_pool() -> List[Optional[str]]:
    """Proxy rotation pool from settings, or [None] for direct egress."""
    raw = getattr(settings, "PROXY_LIST", "") or ""
    urls = [p.strip() for p in raw.split(",") if p.strip()]
    return urls or [None]


def _supports_per_request_proxy() -> bool:
    """True when the installed httpx accepts ``proxy=`` on a request.

    httpx 0.26 (the version this project pins) takes the proxy on the
    *client* only - ``AsyncClient.get()`` has no ``proxy`` keyword. httpx
    0.28 added it to ``request()``/``get()``.

    Passing ``proxy=`` to a 0.26 client raises
    ``TypeError: get() got an unexpected keyword argument 'proxy'`` on the
    first request, which ``fetch_html`` swallowed as a generic failure and
    retried three more times before returning None. That made *every*
    directory source - Sulekha included - look like it was simply returning
    no results, when in fact nothing had ever been fetched.
    """
    try:
        params = inspect.signature(httpx.AsyncClient.request).parameters
    except (AttributeError, TypeError, ValueError):  # pragma: no cover - defensive
        return False
    return "proxy" in params


def looks_blocked(html: Optional[str]) -> bool:
    """True when the response is an interstitial/captcha rather than content.

    The size heuristic used to be "any body under 2 KB is a block stub".
    That is wrong in both directions and expensive: many legitimate pages
    are tiny (a minimal one-page site, a JSON endpoint, an Instagram/FB
    login wall), so every one of them was retried four times with
    exponential backoff - ~7-9 seconds per URL - and then **discarded**.
    The social finder alone cost 6.9s per lead and returned nothing.

    A block page is identified by what it *says*, not by how small it is.
    The size check stays only as a guard for a body that is clearly empty.
    """
    if not html:
        return True
    sample = html[:20000].lower()
    if any(marker in sample for marker in BLOCK_MARKERS):
        return True
    # A body that is essentially empty is not content either - but keep the
    # threshold low so small-but-real pages are never thrown away.
    return len(html.strip()) < 32


async def fetch_html(
    url: str,
    timeout: float = 15.0,
    retries: Optional[int] = None,
    proxy: Optional[str] = None,
    allow_proxy_pool: bool = True,
) -> Optional[str]:
    """Best-effort HTML fetch. Never raises; returns None on any failure.

    Retries on block pages, 403/429/5xx, and network errors, rotating the
    User-Agent (and proxy, when a pool is configured) between attempts so one
    bad fingerprint costs one request rather than the whole source. Backoff is
    exponential with jitter, which keeps a burst of parallel sources from
    synchronising into a thundering herd against the same host.
    """
    if retries is None:
        retries = getattr(settings, "HTTP_MAX_RETRIES", 3)
    backoff = float(getattr(settings, "HTTP_RETRY_BACKOFF", 1.5) or 1.5)

    pool = _proxy_pool() if allow_proxy_pool else [None]
    attempts = max(1, retries + 1)
    last_reason = "unknown"

    # One client per proxy for the whole retry loop, created lazily.
    #
    # A client per *attempt* meant a new TLS handshake and no connection
    # reuse on every single request - the single cheapest performance win
    # in this module. But httpx 0.26 only accepts the proxy on the client,
    # so a per-attempt proxy needs a per-proxy client. Keying the clients
    # by proxy gives both: one reused connection pool for the common
    # no-proxy case, and one client per egress when a pool is configured.
    clients: Dict[Optional[str], httpx.AsyncClient] = {}

    def _client_for(p: Optional[str]) -> httpx.AsyncClient:
        client = clients.get(p)
        if client is None:
            kwargs = dict(
                timeout=timeout,
                follow_redirects=True,
                headers={},
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
            if p:
                kwargs["proxy"] = p
            client = httpx.AsyncClient(**kwargs)
            clients[p] = client
        return client

    # httpx >= 0.28 can take the proxy per request, so a single direct
    # client is enough and the proxy can be rotated per attempt.
    per_request_proxy = _supports_per_request_proxy()

    try:
        for attempt in range(attempts):
            chosen_proxy = proxy or random.choice(pool)
            headers = {
                # Deterministic rotation keyed on the attempt index, so the same
                # attempt is reproducible in tests while still varying in practice.
                "User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)],
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
                # Directories serve different markup to bots that omit these.
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
            try:
                if per_request_proxy:
                    response = await _client_for(None).get(
                        url, headers=headers, proxy=chosen_proxy
                    )
                else:
                    response = await _client_for(chosen_proxy).get(url, headers=headers)

                if response.status_code == 200:
                    body = response.text
                    if looks_blocked(body):
                        last_reason = "blocked_page"
                    else:
                        return body
                elif response.status_code in (403, 429, 503):
                    # Retryable: rate limit or a client fingerprint we can change.
                    last_reason = f"http_{response.status_code}"
                elif 400 <= response.status_code < 500:
                    # A genuine client error (404/410/gone) will not fix itself.
                    logger.debug(f"fetch_html {url} -> HTTP {response.status_code} (not retrying)")
                    return None
                else:
                    last_reason = f"http_{response.status_code}"

            except Exception as e:
                last_reason = f"{type(e).__name__}"

            if attempt < attempts - 1:
                delay = backoff ** attempt + random.uniform(0, 0.5)
                logger.debug(f"fetch_html {url} attempt {attempt + 1} failed ({last_reason}); retry in {delay:.1f}s")
                await asyncio.sleep(delay)

        logger.debug(f"fetch_html {url} gave up after {attempts} attempts ({last_reason})")
        return None
    finally:
        for client in clients.values():
            await client.aclose()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def extract_city(area: Optional[str]) -> Optional[str]:
    """
    Directory sites expect a city, but users describe areas ("Rohini Delhi").
    Falls back to the whole area when no known city is mentioned.
    """
    if not area:
        return None
    lowered = re.sub(r"\s+", " ", area.lower().strip())

    if lowered in CITY_ALIASES:
        return CITY_ALIASES[lowered]

    for city in INDIAN_CITIES:
        if city in lowered:
            return CITY_ALIASES.get(city, city)

    return re.sub(r"\s+", "-", lowered.strip()) or None


def parse_float(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", "."))
    return float(match.group(0)) if match else None


def parse_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def to_soup(html: Optional[str]) -> Optional[BeautifulSoup]:
    if not html:
        return None
    return BeautifulSoup(html, "html.parser")
