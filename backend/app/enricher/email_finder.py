import asyncio
import random
import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple, Any, Optional
from sqlalchemy import select, or_

from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.enricher.people_extraction import (
    extract_executives_from_jsonld,
    extract_executives_from_text,
    extract_people_without_roles,
    merge_executives,
    _strip_testimonials,
)
from app.enricher.seniority import extract_company_profile
from app.sources import in_phone
from app.verifier.smtp_verifier import (
    verify_email,
    verify_email_async,
    verify_batch,
    check_catch_all_domain,
    check_catch_all_domain_async,
)
from app.verifier.email_status import detect_role_account, detect_placeholder_domain
from app.enricher.pattern import generate_candidates

logger = logging.getLogger(__name__)

#: User-Agent strings used for outbound requests, rotated between retries.
#: A single static UA is the easiest fingerprint to block on.
#:
#: ``app.sources.http_utils`` already owns the canonical list; it does not
#: import anything from ``app.enricher``, so reusing it here cannot create a
#: circular import. The fallback keeps this module importable on its own.
try:  # pragma: no cover - defensive import of a shared constant
    from app.sources.http_utils import USER_AGENTS as _SHARED_USER_AGENTS
except Exception:  # pragma: no cover
    _SHARED_USER_AGENTS = ()

CRAWL_USER_AGENTS: Tuple[str, ...] = tuple(_SHARED_USER_AGENTS) or (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
)

#: How many pages of a single site are fetched *concurrently*.
#:
#: The page budget is unaffected: the crawler walks the work queue in
#: batches of at most this size and never fetches more than ``max_pages``
#: distinct URLs in total.
CRAWL_PAGE_CONCURRENCY = 4

#: Retries (on top of the first attempt) for a single page fetch.
CRAWL_FETCH_RETRIES = 2

#: Retries for a single search-engine query.
SEARCH_FETCH_RETRIES = 2

#: Base delay of the exponential backoff between retries (seconds).
RETRY_BACKOFF = 0.8

#: Timeout for the robots.txt lookup - it must never dominate a crawl.
ROBOTS_TIMEOUT = 5.0

#: Upper bound honoured for a robots.txt ``Crawl-delay`` (seconds).
MAX_CRAWL_DELAY = 3.0

#: Token used when matching robots.txt rules against our own requests.
ROBOTS_USER_AGENT = "LeadForgeBot"

#: Transient failures worth another attempt.
RETRYABLE_STATUS = (429, 500, 502, 503, 504)

SITE_HEADERS = {
    "User-Agent": CRAWL_USER_AGENTS[0],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
}

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6789]\d{9}|0?[6789]\d{4}\s*\d{5}|0?[6789]\d{9}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})')

EXCLUDED_EMAIL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.woff', '.pdf')
# Scoped to HTML boilerplate / CDN / example hosts only. This list used to
# include 'google.com', which silently discarded genuine @google.com corporate
# addresses - a real lead lost to a noise filter. Real corporate domains are
# handled by email_status.detect_placeholder_domain, which knows the difference
# between sentry.io/example.com and a company's actual mail domain.
EXCLUDED_EMAIL_DOMAINS = ('sentry.io', 'example.com', 'wixpress.com', 'domain.com', 'email.com', 'schema.org')


# ---------------------------------------------------------------------------
# HTTP plumbing shared by the search stage and the site crawler
# ---------------------------------------------------------------------------

def _build_http_client(timeout: float = 12.0) -> httpx.AsyncClient:
    """A pooled client with browser-ish headers and *verified* TLS.

    A single client pools connections internally, so one client per crawl
    (rather than one per page) is what makes the crawl fast.

    TLS verification is left at httpx's default (on). The old crawler ran
    with ``verify=False``, which is both a MITM hole and a bot signal.
    """
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=SITE_HEADERS,
        limits=httpx.Limits(
            max_connections=CRAWL_PAGE_CONCURRENCY + 2,
            max_keepalive_connections=CRAWL_PAGE_CONCURRENCY + 2,
        ),
    )


def _request_headers(attempt: int) -> Dict[str, str]:
    """Headers for one attempt, rotating the User-Agent between retries."""
    ua = CRAWL_USER_AGENTS[attempt % len(CRAWL_USER_AGENTS)]
    return {
        "User-Agent": ua,
        "Accept": SITE_HEADERS["Accept"],
        "Accept-Language": SITE_HEADERS["Accept-Language"],
    }


def _backoff_delay(attempt: int, base: float = RETRY_BACKOFF) -> float:
    """Exponential backoff with jitter, so parallel crawls do not sync up."""
    return (base * (2 ** attempt)) + random.uniform(0, 0.5)


def _is_tls_error(exc: BaseException) -> bool:
    """True when an exception was caused by a certificate problem."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return "ssl" in text or "certificate" in text


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = CRAWL_FETCH_RETRIES,
    timeout: Optional[float] = None,
) -> Optional[httpx.Response]:
    """GET with retries, exponential backoff, jitter and UA rotation.

    Only transient failures are retried: connection errors, timeouts and
    429/5xx responses. A 404 (or any other 4xx that will not fix itself) is
    returned immediately so the retry budget is not wasted on it.

    Never raises - a failed request comes back as ``None``.
    """
    attempts = max(1, retries + 1)
    last_error: Optional[str] = None

    for attempt in range(attempts):
        try:
            kwargs: Dict[str, Any] = {"headers": _request_headers(attempt)}
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = await client.get(url, **kwargs)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if _is_tls_error(exc):
                logger.warning(
                    "TLS verification failed for %s (%s). The certificate of "
                    "this host must be fixed for enrichment to work.",
                    urlparse(url).netloc, last_error,
                )
            if attempt < attempts - 1:
                await asyncio.sleep(_backoff_delay(attempt))
                continue
            logger.debug("GET %s failed after %d attempts (%s)", url, attempts, last_error)
            return None

        if response.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
            last_error = f"HTTP {response.status_code}"
            logger.debug(
                "GET %s -> %s; retrying", url, response.status_code,
            )
            await asyncio.sleep(_backoff_delay(attempt))
            continue

        return response

    return None


def _normalize_site_url(url: str) -> str:
    """Adds the https:// scheme a bare domain is missing."""
    if not url:
        return ""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def _normalize_crawl_url(url: str) -> str:
    """Canonical key for a URL: no fragment, no trailing slash, lower-case host.

    Used for de-duplication so ``/contact`` and ``/contact/`` are recognised
    as the same page and are never fetched twice.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return ""
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if not netloc:
        return ""
    path = parsed.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    out = f"{scheme}://{netloc}{path}"
    if parsed.query:
        out += f"?{parsed.query}"
    return out


async def _robots_parser(
    client: httpx.AsyncClient,
    origin: str,
    cache: Dict[str, Optional[RobotFileParser]],
) -> Optional[RobotFileParser]:
    """Fetches and caches ``/robots.txt`` for one origin.

    A missing (or unreadable) robots.txt means "no restrictions", which is
    the standard interpretation.
    """
    if origin in cache:
        return cache[origin]

    parser: Optional[RobotFileParser] = None
    try:
        response = await client.get(f"{origin}/robots.txt", timeout=ROBOTS_TIMEOUT)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
    except Exception as exc:
        logger.debug("robots.txt lookup failed for %s: %s", origin, exc)

    cache[origin] = parser
    return parser


async def _robots_allows(
    client: httpx.AsyncClient,
    url: str,
    cache: Dict[str, Optional[RobotFileParser]],
) -> bool:
    """Whether robots.txt permits us to fetch ``url``."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    parser = await _robots_parser(client, origin, cache)
    if parser is None:
        return True
    try:
        return bool(parser.can_fetch(ROBOTS_USER_AGENT, url))
    except Exception:
        return True


async def _respect_crawl_delay(
    client: httpx.AsyncClient,
    url: str,
    cache: Dict[str, Optional[RobotFileParser]],
) -> None:
    """Honours a robots.txt ``Crawl-delay`` (capped so it cannot hang a crawl)."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    parser = await _robots_parser(client, origin, cache)
    if parser is None:
        return
    try:
        delay = parser.crawl_delay(ROBOTS_USER_AGENT)
    except Exception:
        delay = None
    if delay and delay > 0:
        await asyncio.sleep(min(float(delay), MAX_CRAWL_DELAY))

#: Call-to-action and boilerplate phrases that the title regex used to
#: mistake for people's names. "Read more - owner" became the contact
#: "read more" with title "owner", and that garbage then consumed the
#: candidate budget (read.more@domain, call.now@domain).
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
})


def _is_plausible_person_name(name: str) -> bool:
    """Whether a scraped "name" is actually a person.

    Two or three capitalised tokens that are not boilerplate and not a
    known CTA phrase.
    """
    if not name:
        return False
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    if cleaned in _NOT_A_PERSON_NAME:
        return False
    tokens = cleaned.split()
    if len(tokens) not in (2, 3):
        return False
    # Reject page/section words that are never part of a person's name.
    if any(t in ("about", "contact", "home", "terms", "service", "privacy",
                 "policy", "page", "our", "the", "your", "and", "for")
           for t in tokens):
        return False
    return True


def _exec_for_address(email: str, execs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Finds the executive an address plausibly belongs to.

    A shared mailbox (``info@``, ``sales@``) belongs to nobody. A person
    address carries their name (or its initials) in the local part.
    Returns None when no executive can be bound - which is the correct
    answer for a role mailbox.
    """
    from app.enricher.people_extraction import bind_executives_to_email

    if not email or "@" not in email or not execs:
        return None
    local = email.split("@")[0].lower().strip()
    if not local:
        return None
    # A purely alphabetic local part that is a common role word is a mailbox.
    if local in ("contact", "info", "sales", "office", "support", "admin", "hello"):
        return None
    return bind_executives_to_email(email, execs)


def _address_source(email: str, harvested: Any, permutations: List[str],
                    domain: Optional[str]) -> str:
    """Where this address came from.

    Every contact used to be stamped ``multi_source_enricher``, which made it
    impossible to measure the thing that actually matters: how often a
    *guessed* mailbox is right versus a harvested one.
    """
    local = email.split("@")[0].lower()
    if local in ("contact", "info", "sales", "office"):
        return "alias"
    if permutations and email in {p.lower() for p in permutations}:
        return "pattern_guess"
    if domain and email.rpartition("@")[2].lower() == domain.lower():
        return "website_scrape"
    return "web_search"

CONTACT_PRIORITY_KEYWORDS = [
    'contact', 'about', 'reach', 'touch', 'team', 'connect', 'help', 'info', 'support', 'impressum'
]


def decode_cloudflare_email(cf_hex: str) -> str:
    """Decodes Cloudflare email obfuscation hex strings (data-cfemail)."""
    try:
        r = int(cf_hex[:2], 16)
        email = ''.join(chr(int(cf_hex[i:i+2], 16) ^ r) for i in range(2, len(cf_hex), 2))
        return email.strip().lower() if EMAIL_REGEX.match(email.strip()) else ""
    except Exception:
        return ""


def deobfuscate_text_emails(text: str) -> str:
    """Normalizes anti-bot email obfuscations like 'user [at] domain [dot] com'."""
    t = re.sub(r'\[at\]|\(at\)|\bat\b', '@', text, flags=re.IGNORECASE)
    t = re.sub(r'\[dot\]|\(dot\)|\bdot\b', '.', t, flags=re.IGNORECASE)
    return t


def generate_email_permutations(name: str, domain: str) -> List[str]:
    """
    Generates Apollo/Hunter-grade email permutations based on business/contact name and domain.
    Includes corporate executive patterns and high-yield department aliases.
    """
    if not domain or "." not in domain:
        return []

    domain = domain.lower().replace("www.", "").strip()
    permutations: List[str] = []

    # Clean name tokens
    clean = re.sub(r'[^a-zA-Z\s]', ' ', name).lower().strip()
    parts = [p for p in clean.split() if len(p) >= 2 and p not in (
        "limited", "pvt", "ltd", "llc", "inc", "corp", "associates", "agency", "realty", "group", "services"
    )]

    first = parts[0] if parts else "contact"
    last = parts[1] if len(parts) > 1 else ""

    if first and last:
        permutations.extend([
            f"{first}.{last}@{domain}",
            f"{first}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}_{last}@{domain}",
            f"{last}@{domain}",
        ])
    elif first:
        permutations.extend([
            f"{first}@{domain}",
        ])

    # Standard corporate aliases
    permutations.extend([
        f"contact@{domain}",
        f"info@{domain}",
        f"sales@{domain}",
        f"office@{domain}",
        f"support@{domain}",
        f"hello@{domain}",
        f"admin@{domain}",
    ])

    seen = set()
    unique_perms = []
    for p in permutations:
        if p not in seen:
            seen.add(p)
            unique_perms.append(p)

    return unique_perms


def calculate_lead_quality_score(
    business: Any,
    contacts: List[Any],
    icp_profile: Any = None,
) -> Dict[str, Any]:
    """
    Entry point for the 0-100 lead quality score.

    Without an ICP profile this reproduces the legacy
    calculate_lead_quality_score output exactly. With one, the fit and
    intent signals are layered in and the profile's preset decides whether
    a weak web presence is a penalty or an opportunity - which is what
    makes the score *relative to the search* rather than a global
    "completeness" number that says the same thing about every lead.
    """
    from app.qualifier.scorer import score_lead

    result = score_lead(business, contacts, icp_profile)

    extra = getattr(business, "extra_data", None)
    if isinstance(extra, dict) and extra.get("is_claimed", True) is False:
        if "Unclaimed GBP" not in result["badges"]:
            result["badges"].append("Unclaimed GBP")

    return result


def _extract_contacts_from_text(text: str, emails: Set[str], phones: Set[str]) -> None:
    """Adds every email / phone number found in a block of text."""
    for em in EMAIL_REGEX.findall(text):
        em_clean = em.lower().strip(".")
        if any(em_clean.endswith(ext) for ext in EXCLUDED_EMAIL_EXTENSIONS):
            continue
        domain = em_clean.split("@")[-1] if "@" in em_clean else ""
        if domain and not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
            emails.add(em_clean)

    for ph in PHONE_REGEX.findall(text):
        clean_ph = ph[0] if isinstance(ph, tuple) else ph
        digits = re.sub(r'\D', '', clean_ph)
        if 10 <= len(digits) <= 13:
            phones.add(clean_ph.strip())


async def _search_yahoo(
    client: httpx.AsyncClient,
    search_query: str,
    emails: Set[str],
    phones: Set[str],
    websites: List[str],
) -> None:
    """Engine 1: Yahoo Search."""
    try:
        y_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(search_query)}"
        res = await _get_with_retry(client, y_url, retries=SEARCH_FETCH_RETRIES)
        if res is None or res.status_code != 200:
            return
        soup_y = BeautifulSoup(res.text, "html.parser")
        for item in soup_y.select("div.algo"):
            text = item.get_text(" ", strip=True)
            _extract_contacts_from_text(text, emails, phones)
            link = item.select_one("a[href^='http']")
            if link:
                href = link.get("href", "")
                m = re.search(r'/RU=(.*?)/RK=', href)
                target_url = urllib.parse.unquote(m.group(1)) if m else href
                if target_url.startswith("http") and not any(x in target_url for x in [
                    "yahoo.com", "bing.com", "google.com", "facebook.com",
                    "instagram.com", "twitter.com", "youtube.com"
                ]):
                    websites.append(target_url)
    except Exception as y_err:
        logger.debug(f"Yahoo search error: {y_err}")


async def _search_bing(
    client: httpx.AsyncClient,
    clean_name: str,
    clean_location: str,
    emails: Set[str],
    phones: Set[str],
) -> None:
    """Engine 2: Bing Search."""
    try:
        b_url = f"https://www.bing.com/search?q={urllib.parse.quote(f'{clean_name} {clean_location} phone email')}"
        res = await _get_with_retry(client, b_url, retries=SEARCH_FETCH_RETRIES)
        if res is None or res.status_code != 200:
            return
        soup_b = BeautifulSoup(res.text, "html.parser")
        for item in soup_b.select("li.b_algo"):
            text = item.get_text(" ", strip=True)
            _extract_contacts_from_text(text, emails, phones)
    except Exception as b_err:
        logger.debug(f"Bing search error: {b_err}")


async def search_web_for_business_contacts(name: str, location: str = "") -> Dict[str, Any]:
    """
    Searches across Yahoo, Bing, and web directories to discover missing business
    phone numbers, corporate emails, and official websites when not present on Google Maps.
    """
    emails: Set[str] = set()
    phones: Set[str] = set()
    websites: List[str] = []

    # Clean name of trailing keywords (e.g. ":- Real Estate Agent")
    clean_name = re.sub(r'[:|\-·]+.*$', '', name).strip()
    clean_location = re.sub(r'[:|\-·]+.*$', '', location).strip()
    search_query = f'"{clean_name}" {clean_location} phone contact email'.strip()

    try:
        async with _build_http_client(timeout=12.0) as client:
            # Yahoo and Bing are independent requests to two different hosts.
            # They used to be awaited one after the other, so every lead paid
            # for the sum of both engines' latencies. Running them together
            # costs the slower engine instead of the sum - and neither engine
            # can take the other one down with it.
            results = await asyncio.gather(
                _search_yahoo(client, search_query, emails, phones, websites),
                _search_bing(client, clean_name, clean_location, emails, phones),
                return_exceptions=True,
            )
            for res in results:
                if isinstance(res, BaseException):
                    logger.debug("Web search engine failed: %s", res)

    except Exception as e:
        logger.warning(f"Web search discovery error for '{name}': {e}")

    return {
        "emails": list(emails),
        "phones": list(phones),
        "discovered_website": websites[0] if websites else None
    }


#: Titles that actually appear on Indian SMB sites. The old list missed
#: MD, Principal (e.g. "Principal Dentist" - the dental norm), General
#: Manager, Promoter and Chairman, which together cover the majority of
#: owner-operator titles in the target market.
_EXEC_TITLES = [
    r'founder', r'co-founder', r'ceo', r'chief executive officer',
    r'managing director', r'md', r'director', r'principal(?:\s+\w+)?',
    r'general manager', r'manager', r'promoter', r'chairman',
    r'chairperson', r'president', r'owner', r'partner', r'proprietor',
    r'administrator', r'head of \w+', r'vice president', r'vp',
]

#: The separator class includes the em-dash (U+2014), en-dash (U+2013) and
#: bullet (U+2022) - all three are used by Indian SMB sites and all three
#: were silently failing to split name from title.
_TITLE_PATTERN = re.compile(
    r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,2})\s*'
    r'(?:[-\u2013\u2014\u2022|,;:()]|\bis\b|\bas\b|&)\s*('
    + '|'.join(_EXEC_TITLES) + r')\b',
    re.IGNORECASE
)


def _is_x_host(href: str, host: str) -> bool:
    """Whether a link points at ``host`` (or one of its sub-domains).

    The old check was a plain ``"x.com" in href`` substring test, which
    matched every URL that merely *contained* those characters - so a link
    to ``https://www.max.com/`` was filed as a Twitter profile.
    """
    try:
        parsed = urlparse(href)
    except Exception:
        return False
    netloc = (parsed.netloc or "").lower().split(":")[0]
    if not netloc:
        return False
    return netloc == host or netloc.endswith("." + host)


def _extract_page_contacts(
    html_text: str,
    current_url: str,
    base_domain: str,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Every contact signal on one page of HTML.

    Pure function (no network), so the crawler can run it over pages it
    fetched concurrently without any shared mutable state.
    """
    emails: Set[str] = set()
    phones: Set[str] = set()
    whatsapp_links: Set[str] = set()
    socials: Dict[str, str] = {}
    executives: List[Dict[str, str]] = []
    internal_links: List[str] = []

    # 1. Regex email search + deobfuscated text search
    normalized_text = deobfuscate_text_emails(html_text)
    for em in EMAIL_REGEX.findall(normalized_text):
        em_clean = em.lower().strip(".")
        if any(em_clean.endswith(ext) for ext in EXCLUDED_EMAIL_EXTENSIONS):
            continue
        domain = em_clean.split("@")[-1] if "@" in em_clean else ""
        if domain and not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
            emails.add(em_clean)

    # 2. Regex phone search
    for ph in PHONE_REGEX.findall(html_text):
        clean_ph = ph[0] if isinstance(ph, tuple) else ph
        if len(re.sub(r'\D', '', clean_ph)) >= 10:
            phones.add(clean_ph.strip())

    # 3. DOM parsing for Cloudflare emails, mailto:, tel:, WhatsApp, and Socials
    soup = BeautifulSoup(html_text, 'html.parser')

    # Cloudflare email protection decode
    for cf_el in soup.select('[data-cfemail], .__cf_email__'):
        cf_hex = cf_el.get('data-cfemail') or cf_el.get('href', '').split('#')[-1]
        if cf_hex:
            cf_email = decode_cloudflare_email(cf_hex)
            if cf_email and not any(ex in cf_email for ex in EXCLUDED_EMAIL_DOMAINS):
                emails.add(cf_email)

    # Executive detection on about/team pages.
    #
    # Four passes, strongest first: JSON-LD (structured, so trusted
    # outright), then "Name - Title", then "Title: Name", then "Name is a
    # Role". The title-first form is the one the old pattern missed
    # entirely, and it is common on Indian sites ("Proprietor: Mr. Rakesh
    # Gupta").
    #
    # Testimonials and reviews are stripped first: a customer writing "I
    # bought my office from Mr. Omkar" would otherwise add a customer to
    # the People table.
    _strip_testimonials(soup)
    text_clean = soup.get_text(" ", strip=True)
    executives.extend(
        merge_executives(
            extract_executives_from_jsonld(soup),
            extract_executives_from_text(text_clean, company_name),
            extract_people_without_roles(text_clean, company_name),
        )
    )

    for link in soup.find_all('a', href=True):
        href = link['href'].strip()
        lowered = href.lower()

        # Mailto links
        if lowered.startswith('mailto:'):
            em = href[href.lower().index('mailto:') + len('mailto:'):].split('?')[0].strip()
            if EMAIL_REGEX.match(em):
                em_clean = em.lower()
                domain = em_clean.rpartition("@")[2]
                if domain and not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
                    emails.add(em_clean)

        # Tel links
        elif lowered.startswith('tel:'):
            ph = href[href.lower().index('tel:') + len('tel:'):].split('?')[0].strip()
            if len(re.sub(r'\D', '', ph)) >= 10:
                phones.add(ph)

        # WhatsApp links
        elif 'wa.me' in href or 'api.whatsapp.com' in href:
            whatsapp_links.add(href)

        # Social Profiles
        elif 'linkedin.com/company' in href or 'linkedin.com/in' in href:
            socials['linkedin'] = href
        elif 'facebook.com' in href and not any(x in href for x in ['sharer', 'dialog']):
            socials['facebook'] = href
        elif 'instagram.com' in href and not any(x in href for x in ['share', 'p/']):
            socials['instagram'] = href
        elif 'twitter.com' in href or _is_x_host(href, 'x.com'):
            socials['twitter'] = href
        elif 'youtube.com' in href:
            socials['youtube'] = href

        # Internal page discovery - external links are never followed, so the
        # page budget is never spent on somebody else's website.
        else:
            full_next = urljoin(current_url, href)
            next_parsed = urlparse(full_next)
            next_domain = next_parsed.netloc.lower().replace("www.", "")

            if next_domain == base_domain:
                internal_links.append(full_next)

    return {
        "emails": emails,
        "phones": phones,
        "whatsapp": whatsapp_links,
        "socials": socials,
        "executives": executives,
        "internal_links": internal_links,
        "company_profile": extract_company_profile(html_text),
    }


def _merge_company_profile(
    target: Dict[str, Any],
    addition: Optional[Dict[str, Any]],
) -> None:
    """Folds one page's company profile into the crawl's running total.

    The first page that states a value wins for the numeric fields, and
    technologies accumulate. A later page that merely repeats a number
    ("© 2024, 50 employees") must not overwrite a specific one.
    """
    if not addition:
        return
    for key in ("employee_count", "size_bucket", "revenue", "revenue_band"):
        if target.get(key) is None and addition.get(key) is not None:
            target[key] = addition[key]
    techs = set(target.get("technologies") or [])
    techs.update(addition.get("technologies") or [])
    if techs:
        target["technologies"] = sorted(techs)


async def _fetch_page_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetches one page and returns its HTML (``None`` on any failure)."""
    response = await _get_with_retry(client, url, retries=CRAWL_FETCH_RETRIES)
    if response is None or response.status_code != 200:
        return None
    content_type = response.headers.get("content-type", "")
    # A missing content-type is not a reason to throw a real page away; a
    # non-HTML content type is.
    if content_type and ("text/html" not in content_type and "xhtml" not in content_type):
        return None
    return response.text


async def _crawl_with_client(
    client: httpx.AsyncClient,
    url: str,
    max_pages: int,
    homepage_html: Optional[str],
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """The crawl itself. See :func:`crawl_website_for_contacts`."""
    emails: Set[str] = set()
    phones: Set[str] = set()
    whatsapp_links: Set[str] = set()
    socials: Dict[str, str] = {}
    executives: List[Dict[str, str]] = []
    #: Company size / revenue / technology, merged across the pages crawled.
    company_profile: Dict[str, Any] = {}

    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    #: Normalised URLs that have been *scheduled*. A URL is reserved BEFORE
    #: the request goes out, so a page can never be fetched twice - not when
    #: the same link appears twice on a page, and not when two pages of the
    #: same batch both link to it.
    visited: Set[str] = set()
    #: URLs already sitting in one of the queues (stops duplicate entries).
    queued: Set[str] = set()
    priority_queue: List[str] = []
    to_visit: List[str] = []
    robots_cache: Dict[str, Optional[RobotFileParser]] = {}

    #: The homepage is handled on its own (it may already have been supplied
    #: by the caller) so its links can seed the next batch.
    pending: List[Tuple[str, Optional[str]]] = [(url, homepage_html)]
    attempted = 0
    homepage_used = homepage_html

    while attempted < max_pages and (pending or priority_queue or to_visit):
        batch: List[Tuple[str, Optional[str]]] = []
        batch_size = max(1, min(CRAWL_PAGE_CONCURRENCY, max_pages - attempted))

        if pending:
            batch = pending[:1]
            pending = []
        else:
            # Contact/about pages first (same priority the serial crawler
            # used), then whatever else the site links to.
            while priority_queue and len(batch) < batch_size:
                batch.append((priority_queue.pop(0), None))
            while to_visit and len(batch) < batch_size:
                batch.append((to_visit.pop(0), None))

        if not batch:
            break

        # Reserve the URLs *before* fetching them.
        targets: List[Tuple[str, Optional[str]]] = []
        for target, pre_html in batch:
            norm = _normalize_crawl_url(target)
            if not norm or norm in visited:
                continue
            visited.add(norm)
            targets.append((target, pre_html))

        if not targets:
            continue

        # robots.txt
        allowed: List[Tuple[str, Optional[str]]] = []
        for target, pre_html in targets:
            if pre_html is not None:
                allowed.append((target, pre_html))
                continue
            if await _robots_allows(client, target, robots_cache):
                allowed.append((target, None))
            else:
                logger.debug("robots.txt disallows %s", target)

        if not allowed:
            continue

        attempted += len(allowed)
        await _respect_crawl_delay(client, allowed[0][0], robots_cache)

        # Pages the caller already fetched are used as-is; the rest are
        # fetched concurrently over the one pooled client.
        html_results: List[Optional[str]] = [None] * len(allowed)
        fetch_indexes: List[int] = []
        for idx, (_target, pre_html) in enumerate(allowed):
            if pre_html is not None:
                html_results[idx] = pre_html
            else:
                fetch_indexes.append(idx)

        if fetch_indexes:
            if len(fetch_indexes) == 1:
                fetched = [await _fetch_page_html(client, allowed[fetch_indexes[0]][0])]
            else:
                fetched = await asyncio.gather(
                    *[_fetch_page_html(client, allowed[i][0]) for i in fetch_indexes]
                )
            for idx, html_text in zip(fetch_indexes, fetched):
                html_results[idx] = html_text

        for (target, _pre_html), html_text in zip(allowed, html_results):
            if not html_text:
                continue
            if _normalize_crawl_url(target) == _normalize_crawl_url(url) and homepage_used is None:
                homepage_used = html_text

            data = _extract_page_contacts(html_text, target, base_domain, company_name)
            emails.update(data["emails"])
            phones.update(data["phones"])
            whatsapp_links.update(data["whatsapp"])
            socials.update(data["socials"])
            executives.extend(data["executives"])
            _merge_company_profile(company_profile, data.get("company_profile"))

            for link in data["internal_links"]:
                norm = _normalize_crawl_url(link)
                if not norm or norm in visited or norm in queued:
                    continue
                queued.add(norm)
                path_lower = urlparse(link).path.lower()
                if any(kw in path_lower for kw in CONTACT_PRIORITY_KEYWORDS):
                    priority_queue.append(link)
                elif len(to_visit) < 10:
                    to_visit.append(link)

    return {
        "emails": list(emails),
        "phones": list(phones),
        "whatsapp": list(whatsapp_links)[0] if whatsapp_links else None,
        "socials": socials,
        "executives": merge_executives(executives)[:8],
        "company_profile": company_profile,
        "homepage_html": homepage_used,
    }


async def crawl_website_for_contacts(
    url: str,
    max_pages: int = 4,
    homepage_html: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    company_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crawls a target business website, prioritizing contact/about subpages,
    and extracts emails, phone numbers, WhatsApp links, and social links.

    ``homepage_html`` lets the caller supply a homepage it has already
    fetched, so the homepage is downloaded once per lead and can be shared
    with the social finder instead of being fetched twice.

    ``client`` lets the caller supply a pooled client. When omitted, one
    client is created and reused for every page of the crawl.

    ``company_name`` is the business's own name. Its words are trimmed off
    candidate people, so "Pundits ANERI MEHTA Co" at "Real Estate Pundits"
    resolves to the person "ANERI MEHTA".
    """
    if not url:
        return {"emails": [], "phones": [], "whatsapp": None, "socials": {},
                "executives": [], "homepage_html": None}

    url = _normalize_site_url(url)

    if client is not None:
        return await _crawl_with_client(
            client, url, max_pages, homepage_html, company_name
        )

    async with _build_http_client(timeout=12.0) as owned_client:
        return await _crawl_with_client(
            owned_client, url, max_pages, homepage_html, company_name
        )


async def _probe_business_health_concurrent(business: Any, country: str = "IN") -> Dict[str, Any]:
    """Runs the two network probes of ``probe_business_health`` in parallel.

    ``app.qualifier.signals.probe_business_health`` awaits the website
    health probe and *then* the Facebook Ad Library probe. The two are
    completely independent - a HEAD/GET of the company's own site and a
    fetch of a public Facebook page - so serialising them doubles the
    network wait of every enriched lead.

    ``app/qualifier/`` is outside the enricher package, so instead of
    editing it we call the very same probes here with ``asyncio.gather``.
    The merged patch has exactly the same shape as the serial version.
    """
    try:
        from app.qualifier import signals
    except Exception:
        from app.qualifier.signals import probe_business_health
        return await probe_business_health(business, country=country)

    website_probe = getattr(signals, "_probe_website_health", None)
    ads_probe = getattr(signals, "_probe_facebook_ads", None)
    if not callable(website_probe) or not callable(ads_probe):
        # The probe module changed shape - fall back to its own entry point.
        return await signals.probe_business_health(business, country=country)

    website = getattr(business, "website", None)
    name = getattr(business, "name", "") or ""

    jobs = []
    if website:
        jobs.append(website_probe(website))
    jobs.append(ads_probe(name, country=country))

    results = await asyncio.gather(*jobs, return_exceptions=True)

    patch: Dict[str, Any] = {}
    for res in results:
        if isinstance(res, BaseException):
            logger.debug("Health probe failed: %s", res)
            continue
        if isinstance(res, dict):
            patch.update(res)
    return patch


async def enrich_business_by_id(business_id: int) -> Dict[str, Any]:
    """
    Multi-source lead enrichment:
    1. Searches the open web (DuckDuckGo/web engines) for company emails, phones, and official websites.
    2. If website exists or was discovered, crawls /contact, /about, /team pages.
    3. Verifies email deliverability via DNS MX and SMTP handshakes.
    4. Updates Business phone/website and creates/updates Contacts with WhatsApp links.
    """
    async with async_session_maker() as db:
        business = await db.get(Business, business_id)
        if not business:
            return {"error": "Business not found"}

        all_emails: Set[str] = set()
        all_phones: Set[str] = set()
        discovered_socials: Dict[str, str] = {}
        discovered_whatsapp: Optional[str] = None

        # Step 1: Search the web for missing contact details
        location = business.address or ""
        web_contacts = await search_web_for_business_contacts(business.name, location)
        for em in web_contacts.get("emails", []):
            all_emails.add(em)
        for ph in web_contacts.get("phones", []):
            all_phones.add(ph)

        # If business had no website, adopt discovered website
        if not business.website and web_contacts.get("discovered_website"):
            business.website = web_contacts.get("discovered_website")
            logger.info(f"Discovered official website for {business.name}: {business.website}")

        # Step 2: Crawl website if present
        #
        # The homepage is downloaded ONCE here and the same HTML is handed to
        # both the crawler and the social finder below. It used to be fetched
        # twice per lead (once by the crawler, once by social_finder) for the
        # exact same page.
        crawl_res: Dict[str, Any] = {}
        homepage_html: Optional[str] = None
        if business.website:
            try:
                site_url = _normalize_site_url(business.website)
                async with _build_http_client(timeout=12.0) as site_client:
                    homepage_html = await _fetch_page_html(site_client, site_url)
                    crawl_res = await crawl_website_for_contacts(
                        site_url,
                        homepage_html=homepage_html,
                        client=site_client,
                        company_name=business.name,
                    )
                if not homepage_html:
                    homepage_html = crawl_res.get("homepage_html")
                for em in crawl_res.get("emails", []):
                    all_emails.add(em)
                for ph in crawl_res.get("phones", []):
                    all_phones.add(ph)
                if crawl_res.get("whatsapp"):
                    discovered_whatsapp = crawl_res.get("whatsapp")
                if crawl_res.get("socials"):
                    discovered_socials.update(crawl_res.get("socials"))
                # Company size / revenue / technology, read off the company's
                # own site. These are the attributes an ICP is expressed in
                # ("11-50 employees, over 10Cr turnover, uses Shopify"), so
                # without them the filter can only be "has an email".
                profile = crawl_res.get("company_profile") or {}
                if profile:
                    if profile.get("employee_count") is not None:
                        business.employee_count = profile["employee_count"]
                        business.size_bucket = profile.get("size_bucket")
                    if profile.get("revenue") is not None:
                        business.revenue = profile["revenue"]
                        business.revenue_band = profile.get("revenue_band")
                    if profile.get("technologies"):
                        business.technologies = profile["technologies"]
            except Exception as crawl_err:
                logger.warning(f"Error crawling website for {business.name}: {crawl_err}")

        # Step 2.5: Social enrichment — Stage A (website-derived + JSON-LD sameAs)
        # always on; Stage B (direct platform search) only behind the opt-in flag.
        try:
            from app.enricher.social_finder import (
                find_business_socials,
                probe_direct_socials,
                upsert_social_profiles,
            )
            from app.config import settings

            # An empty string means "we already fetched the homepage and got
            # nothing" - it stops the social finder from downloading the same
            # page a second time.
            merged_socials = await find_business_socials(
                business,
                homepage_html=homepage_html if homepage_html is not None else "",
                contact_socials=discovered_socials,
            )
            provenance = "website"
            if settings.SOCIAL_DIRECT:
                direct_socials = await probe_direct_socials(business)
                for platform, url in direct_socials.items():
                    merged_socials.setdefault(platform, url)
                if direct_socials:
                    provenance = "direct"
            if merged_socials:
                await upsert_social_profiles(db, business.id, merged_socials, provenance=provenance)
                discovered_socials.update(merged_socials)
        except Exception as social_err:
            logger.debug(f"Social enrichment skipped for {business.name}: {social_err}")

        # Step 2.6: Apollo-Grade Waterfall Permutations & Catch-All Validation
        #: Filled in by the permutation stage below; reused by the contact
        #: stage so an address confirmed by the batch is not re-probed.
        batch: Dict[str, Any] = {}
        learned_pattern: Optional[str] = None
        learned_confidence: float = 0.0
        #: Defined here (not only inside the ``business.website`` branch):
        #: a lead with no website but an email from the web search used to
        #: raise NameError in the contact stage below and lose the whole lead.
        permutations: List[str] = []
        w_domain: Optional[str] = None
        if business.website:
            try:
                web_for_domain = business.website if business.website.startswith("http") else f"https://{business.website}"
                parsed_w = urlparse(web_for_domain)
                w_domain = parsed_w.netloc.lower().replace("www.", "").strip()
                if w_domain and "." in w_domain and not any(ex in w_domain for ex in EXCLUDED_EMAIL_DOMAINS):
                    # Use EVERY executive we found, not just the first two. The
                    # pattern learner needs the full set to confirm a
                    # template, and a seed belonging to the third exec used to
                    # be discarded entirely.
                    person_names = []
                    for ex in (crawl_res.get("executives", []) or []):
                        toks = (ex.get("name", "") or "").split()
                        if toks:
                            person_names.append((toks[0], " ".join(toks[1:])))
                    seeds = [e for e in all_emails if e.rpartition("@")[2].lower() == w_domain]
                    permutations, learned_pattern, learned_conf = generate_candidates(
                        w_domain, person_names=person_names or None, seeds=seeds,
                    )
                    if not person_names:
                        permutations = [q for q in permutations if q.split("@")[0] in (
                            "contact", "info", "sales", "office")]

                    # ONE batch, ONE MX connection per domain.
                    #
                    # The old flow opened 2-5 separate MX connections per lead
                    # (a standalone catch-all probe, then the batch, then a
                    # per-address verify loop that re-probed addresses the
                    # batch had just confirmed) and performed 3-8 DNS lookups.
                    # That is both slow and a good way to get the sending IP
                    # blocklisted by port-25 rate limiting.
                    to_verify = [c for c in permutations if c not in all_emails]
                    batch = await verify_batch(to_verify) if to_verify else {}
                    # The batch already probes the domain for catch-all, so a
                    # separate probe would be a third connection to the same MX.
                    is_catch_all = await check_catch_all_domain_async(w_domain)

                    found_perms = 0
                    for cand in permutations:
                        if cand in all_emails:
                            continue
                        if not is_catch_all:
                            cand_res = batch.get(cand)
                            v_ok = cand_res.is_deliverable if cand_res else False
                            v_stat = cand_res.status.value if cand_res else "unknown"
                            # Strict only: adopt a permuted mailbox only when the
                            # SMTP handshake positively confirmed it. The old
                            # "valid_mx" status (valid merely because port 25 was
                            # blocked) was removed by the verifier rewrite - it was
                            # a false-positive generator.
                            if v_ok and v_stat == "valid":
                                all_emails.add(cand)
                                found_perms += 1
                                if found_perms >= 3:
                                    break
                        else:
                            # On catch-all domains, adopt high-yield department addresses
                            alias = cand.split("@")[0]
                            if alias in ("contact", "info", "sales", "office"):
                                all_emails.add(cand)
                                found_perms += 1
                                if found_perms >= 2:
                                    break
            except Exception as perm_err:
                logger.debug(f"Waterfall permutation check for {business.name}: {perm_err}")

        # Update business phone if missing
        if not business.phone and all_phones:
            business.phone = list(all_phones)[0]

        # Step 3: Process and verify each discovered email
        verified_count = 0
        # Addresses we already verified as part of the permutation batch - do
        # not open a second connection to the same MX to confirm them again.
        pre_verified: Dict[str, Any] = dict(batch)
        # Existing contacts for this business, fetched once instead of one
        # SELECT per discovered address.
        existing_by_email: Dict[str, Contact] = {}
        if all_emails:
            for contact in (await db.execute(
                select(Contact).where(
                    Contact.business_id == business.id,
                    Contact.email.in_(list(all_emails)),
                )
            )).scalars().all():
                if contact.email:
                    existing_by_email[contact.email.lower()] = contact

        #: The people identified on the company's own site.
        #:
        #: Assigned here, outside the per-address loop, because it is also
        #: needed when there are no addresses at all - a business whose site
        #: names its proprietor but whose mailbox could not be found still
        #: has a decision maker.
        execs = crawl_res.get("executives", []) if business.website else []

        for email in all_emails:
            existing_contact = existing_by_email.get(email.lower())

            # Use the rich result, not the (bool, str) shim, so sub-status,
            # confidence, MX host and role/free flags are persisted. The shim
            # collapses 20 states into one bool and loses the explanation.
            #
            # The async variant is mandatory here: the sync version performs a
            # DNS lookup, a TCP connect and up to three RCPT probes with an
            # 8-second timeout, all *inside* an async def - which freezes the
            # entire event loop (and therefore the API and the reply poller)
            # for the duration of every send.
            result = pre_verified.get(email)
            if result is None:
                result = await verify_email_async(email)
                pre_verified[email] = result

            v_status = result.status.value
            #: "Verified" means the SMTP handshake positively confirmed the
            #: mailbox. ``is_deliverable`` also covers role accounts and free
            #: providers, which are classified with no network call at all -
            #: so ``info@`` used to be stamped "verified" and awarded the full
            #: 30-point "Verified Email" score without ever being probed.
            is_valid = (v_status == "valid")
            is_deliverable = result.is_deliverable
            if is_valid:
                verified_count += 1

            clean_phone = in_phone.to_e164(
                business.phone or (list(all_phones)[0] if all_phones else None)
            )

            # Bind an executive to THIS address only when the address plausibly
            # belongs to them.
            #
            # The old code took ``execs[0]`` for *every* address, so
            # ``info@acme.in`` was stored with ``first_name="Rajesh"`` and
            # ``title="Founder"`` - a contact that was simultaneously a role
            # mailbox and a named person. The sender then wrote "Hi Rajesh" to
            # a shared mailbox. And with no executive found, the fallback was
            # the *business* name, producing "Hi Apex," for Apex Realty
            # Solutions.
            exec_match = _exec_for_address(email, execs)
            c_first = exec_match["name"].split()[0] if exec_match else None
            c_last = (" ".join(exec_match["name"].split()[1:])
                      if exec_match and len(exec_match["name"].split()) > 1 else None)
            c_title = exec_match["title"] if exec_match else None

            # Person vs role: a discovered executive name means this address
            # belongs to a human. A shared mailbox (info@) is still a lead but
            # must not be counted as a person found.
            is_role = result.is_role or (exec_match is None and detect_role_account(email.split("@")[0]))
            if not is_role and exec_match is None and detect_role_account(email.split("@")[0]):
                is_role = True

            #: Where this address came from, so guess-vs-harvest hit rate can
            #: actually be measured.
            address_source = _address_source(email, all_emails, permutations, w_domain)
            contact_extra: Dict[str, Any] = {}
            if learned_pattern:
                contact_extra["pattern"] = learned_pattern
                contact_extra["pattern_confidence"] = learned_confidence
            if address_source == "pattern_guess":
                contact_extra["is_guess"] = True

            if not existing_contact:
                new_contact = Contact(
                    business_id=business.id,
                    first_name=c_first,
                    last_name=c_last,
                    title=c_title,
                    # A real human was found on the company's own site only
                    # when an executive name was matched to this address. A
                    # role mailbox (info@, sales@) is a company-level
                    # target, not a person.
                    person_identified=bool(exec_match) and not is_role,
                    email=email,
                    phone=in_phone.to_e164(business.phone or (list(all_phones)[0] if all_phones else None))
                         or (business.phone or (list(all_phones)[0] if all_phones else None)),
                    whatsapp_link=discovered_whatsapp or in_phone.whatsapp_link(
                        business.phone or (list(all_phones)[0] if all_phones else None)
                    ),
                    social_links=discovered_socials,
                    is_verified=is_valid,
                    verification_status=v_status,
                    verification_sub_status=result.sub_status,
                    verification_confidence=result.confidence,
                    verification_detail=result.detail,
                    mx_host=result.mx_host,
                    is_role_account=is_role,
                    is_free_email=result.is_free,
                    preferred_channel=in_phone.preferred_channel(
                        business.phone or (list(all_phones)[0] if all_phones else None)
                    ),
                    source=address_source,
                    extra_data=contact_extra or None,
                    verified_at=datetime.now(timezone.utc) if is_valid else None,
                )
                db.add(new_contact)
            else:
                existing_contact.is_verified = is_valid
                existing_contact.verification_status = v_status
                existing_contact.verification_sub_status = result.sub_status
                existing_contact.verification_confidence = result.confidence
                existing_contact.verification_detail = result.detail
                existing_contact.mx_host = result.mx_host
                existing_contact.is_role_account = is_role
                existing_contact.is_free_email = result.is_free
                existing_contact.verified_at = datetime.now(timezone.utc) if is_valid else None
                if exec_match:
                    existing_contact.first_name = c_first
                    existing_contact.last_name = c_last
                    existing_contact.title = c_title
                    existing_contact.person_identified = not is_role
                if discovered_socials:
                    existing_contact.social_links = discovered_socials
                if discovered_whatsapp and not existing_contact.whatsapp_link:
                    existing_contact.whatsapp_link = discovered_whatsapp

        # People who were identified on the website but whose email we do
        # not have yet.
        #
        # This is the single biggest lever on the People table. A business
        # whose site says "Rakesh Gupta - Proprietor" has told us who the
        # decision maker is, even when the mailbox is role-only, the domain
        # is catch-all, or the guessed address fails verification. Dropping
        # that person on the floor because no email came back is what left
        # the People table with 13 rows out of 149 businesses.
        if execs:
            bound_names = {
                (c.first_name or "").strip().lower()
                for c in (await db.execute(
                    select(Contact).where(Contact.business_id == business.id)
                )).scalars().all()
            }
            for ex in execs:
                ex_name = (ex.get("name") or "").strip()
                ex_title = (ex.get("title") or "").strip()
                if not ex_name:
                    continue
                if ex_name.lower() in bound_names:
                    continue
                parts = ex_name.split()
                person = Contact(
                    business_id=business.id,
                    first_name=parts[0],
                    last_name=" ".join(parts[1:]) if len(parts) > 1 else None,
                    title=ex_title or None,
                    person_identified=True,
                    email=None,
                    phone=in_phone.to_e164(business.phone) if business.phone else None,
                    whatsapp_link=in_phone.whatsapp_link(business.phone),
                    preferred_channel=in_phone.preferred_channel(business.phone),
                    source="website_executive",
                    verification_status="unverified",
                    extra_data={
                        "contact_kind": "person",
                        "identified_from": "website",
                        "email_status": "no_address_found",
                        **({"role_unknown": True} if not ex_title else {}),
                    },
                )
                db.add(person)
                bound_names.add(ex_name.lower())

        # If no email found but phone or WhatsApp found, ensure primary contact exists
        if not all_emails:
            stmt = select(Contact).where(Contact.business_id == business.id)
            res = await db.execute(stmt)
            existing_contact = res.scalars().first()
            if existing_contact:
                if all_phones and not existing_contact.phone:
                    existing_contact.phone = in_phone.to_e164(list(all_phones)[0]) or list(all_phones)[0]
                    existing_contact.whatsapp_link = in_phone.whatsapp_link(list(all_phones)[0])
                    existing_contact.preferred_channel = in_phone.preferred_channel(list(all_phones)[0])
            elif business.phone:
                # Phone-only lead: no email was found, so this contact exists purely
                # for the WhatsApp/call channel, which is the primary India channel.
                # It is still the *business* as an outreach target - no human has
                # been identified, so no name is invented.
                c = Contact(
                    business_id=business.id,
                    first_name=None,
                    last_name=None,
                    title=None,
                    person_identified=False,
                    phone=in_phone.to_e164(business.phone) or business.phone,
                    whatsapp_link=in_phone.whatsapp_link(business.phone),
                    preferred_channel=in_phone.preferred_channel(business.phone),
                    extra_data={
                        "contact_kind": "business",
                        "line_type": (
                            "mobile" if in_phone.is_mobile(business.phone)
                            else "landline" if in_phone.is_landline(business.phone)
                            else None
                        ),
                        "dnd_scrub": in_phone.scrub_dnd(business.phone),
                        "city_from_phone": in_phone.city_from_phone(business.phone),
                    },
                    source="multi_source_enricher",
                    verification_status="unverified"
                )
                db.add(c)

        # Step 4: Calculate Lead Quality Score & persist
        icp_profile = None
        if business.icp_profile_id:
            from app.models.icp_profile import ICPProfile
            icp_profile = await db.get(ICPProfile, business.icp_profile_id)

        # Network-dependent fit signals (SSL, site freshness, ad spend) are only
        # probed for ICP-driven enrichment and cached so scoring stays repeatable.
        if icp_profile is not None:
            try:
                health_patch = await _probe_business_health_concurrent(business)
                base_extra = dict(business.extra_data) if (business.extra_data and isinstance(business.extra_data, dict)) else {}
                base_extra.update({k: v for k, v in health_patch.items() if v is not None})
                business.extra_data = base_extra
            except Exception as probe_err:
                logger.debug(f"Health probe skipped for {business.name}: {probe_err}")

        stmt = select(Contact).where(Contact.business_id == business.id)
        res_contacts = await db.execute(stmt)
        final_contacts = res_contacts.scalars().all()

        from app.qualifier.scorer import score_lead
        lead_scoring = score_lead(business, final_contacts, icp_profile)
        base_extra = dict(business.extra_data) if (business.extra_data and isinstance(business.extra_data, dict)) else {}
        base_extra["lead_score"] = lead_scoring["score"]
        base_extra["lead_tier"] = lead_scoring["tier"]
        base_extra["lead_badges"] = lead_scoring["badges"]
        business.extra_data = base_extra
        # Record that this lead has been enriched, so "enrich everything" can
        # skip it next time instead of re-enriching the same newest rows.
        business.enriched_at = datetime.now(timezone.utc)

        if icp_profile is not None:
            business.icp_fit = {
                "score": lead_scoring["score"],
                "tier": lead_scoring["tier"],
                "badges": lead_scoring["badges"],
                "signal_breakdown": lead_scoring["signal_breakdown"],
                "min_score": icp_profile.min_score,
            }

        await db.commit()
        return {
            "business_id": business_id,
            "name": business.name,
            "emails_found": len(all_emails),
            "verified_emails": verified_count,
            "phones_found": len(all_phones),
            "website": business.website,
            "socials": discovered_socials,
            "lead_score": lead_scoring["score"],
            "lead_tier": lead_scoring["tier"],
            "lead_badges": lead_scoring["badges"]
        }


async def enrich_all_pending_businesses(limit: int = 50) -> int:
    """
    Enriches all businesses across the web and their websites to uncover missing
    emails, phone numbers, and WhatsApp contacts.

    It now targets leads that have actually NOT been enriched. It used to
    take the newest N rows by id, so running it twice re-enriched exactly
    the same leads - burning the same crawl budget and SMTP probes - and
    never reached the older leads that still had no email at all.
    """
    count = 0
    async with async_session_maker() as db:
        stmt = (
            select(Business)
            .where(
                or_(
                    Business.enriched_at.is_(None),
                    Business.enriched_at < datetime.now(timezone.utc) - timedelta(days=30),
                )
            )
            .order_by(Business.enriched_at.asc().nullsfirst())
            .limit(limit)
        )
        res = await db.execute(stmt)
        businesses = res.scalars().all()

        for b in businesses:
            try:
                await enrich_business_by_id(b.id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to enrich business {b.id}: {e}")

    return count
