import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse
from urllib.parse import urlparse, urljoin
import logging
from datetime import datetime, timezone
from typing import Dict, List, Set, Any, Optional
from sqlalchemy import select

from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
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

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6789]\d{9}|0?[6789]\d{4}\s*\d{5}|0?[6789]\d{9}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})')

EXCLUDED_EMAIL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.woff', '.pdf')
# Scoped to HTML boilerplate / CDN / example hosts only. This list used to
# include 'google.com', which silently discarded genuine @google.com corporate
# addresses - a real lead lost to a noise filter. Real corporate domains are
# handled by email_status.detect_placeholder_domain, which knows the difference
# between sentry.io/example.com and a company's actual mail domain.
EXCLUDED_EMAIL_DOMAINS = ('sentry.io', 'example.com', 'wixpress.com', 'domain.com', 'email.com', 'schema.org')

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
    address carries their name (or its first letter) in the local part.
    Returns None when no executive can be bound - which is the correct
    answer for a role mailbox.
    """
    if not email or "@" not in email or not execs:
        return None
    local = email.split("@")[0].lower().strip()
    if not local or local in _NOT_A_PERSON_NAME:
        return None
    # A purely alphabetic local part that is a common role word is a mailbox.
    if local in ("contact", "info", "sales", "office", "support", "admin", "hello"):
        return None

    tokens = [t for t in re.split(r"[._+\-]", local) if t]
    for ex in execs:
        name = (ex.get("name") or "").strip()
        if not name:
            continue
        parts = name.lower().split()
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        if first and first in tokens:
            return ex
        if last and last in tokens:
            return ex
        # Initials: "rsharma" for Rajesh Sharma.
        if first and last and len(first) == 1 and tokens and tokens[0] == first:
            return ex
    return None


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


def calculate_lead_quality_score(business: Any, contacts: List[Any]) -> Dict[str, Any]:
    """
    Legacy entry point for the 0-100 lead quality score.

    Preserved as a thin wrapper over the weighted qualifier model so existing
    callers keep producing identical scores and badges; it is equivalent to
    scoring without an attached ICP profile.
    """
    from app.qualifier.scorer import score_lead

    result = score_lead(business, contacts)

    extra = getattr(business, "extra_data", None)
    if isinstance(extra, dict) and extra.get("is_claimed", True) is False:
        if "Unclaimed GBP" not in result["badges"]:
            result["badges"].append("Unclaimed GBP")

    return result


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

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def _extract_from_text(text: str):
        for em in EMAIL_REGEX.findall(text):
            em_clean = em.lower().strip(".")
            if not any(em_clean.endswith(ext) for ext in EXCLUDED_EMAIL_EXTENSIONS):
                domain = em_clean.split("@")[-1] if "@" in em_clean else ""
                if domain and not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
                    emails.add(em_clean)

        for ph in PHONE_REGEX.findall(text):
            clean_ph = ph[0] if isinstance(ph, tuple) else ph
            digits = re.sub(r'\D', '', clean_ph)
            if 10 <= len(digits) <= 13:
                phones.add(clean_ph.strip())

    try:
        async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True, verify=False) as client:
            # Engine 1: Yahoo Search
            try:
                y_url = f"https://search.yahoo.com/search?p={urllib.parse.quote(search_query)}"
                res_y = await client.get(y_url)
                if res_y.status_code == 200:
                    soup_y = BeautifulSoup(res_y.text, "html.parser")
                    for item in soup_y.select("div.algo"):
                        text = item.get_text(" ", strip=True)
                        _extract_from_text(text)
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
                logger.debug(f"Yahoo search error for '{name}': {y_err}")

            # Engine 2: Bing Search
            try:
                b_url = f"https://www.bing.com/search?q={urllib.parse.quote(f'{clean_name} {clean_location} phone email')}"
                res_b = await client.get(b_url)
                if res_b.status_code == 200:
                    soup_b = BeautifulSoup(res_b.text, "html.parser")
                    for item in soup_b.select("li.b_algo"):
                        text = item.get_text(" ", strip=True)
                        _extract_from_text(text)
            except Exception as b_err:
                logger.debug(f"Bing search error for '{name}': {b_err}")

    except Exception as e:
        logger.warning(f"Web search discovery error for '{name}': {e}")

    return {
        "emails": list(emails),
        "phones": list(phones),
        "discovered_website": websites[0] if websites else None
    }


async def crawl_website_for_contacts(url: str, max_pages: int = 4) -> Dict[str, Any]:
    """
    Crawls a target business website, prioritizing contact/about subpages,
    and extracts emails, phone numbers, WhatsApp links, and social links.
    """
    if not url:
        return {"emails": [], "phones": [], "whatsapp": None, "socials": {}}

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    emails: Set[str] = set()
    phones: Set[str] = set()
    whatsapp_links: Set[str] = set()
    socials: Dict[str, str] = {}
    visited: Set[str] = set()
    executives: List[Dict[str, str]] = []

    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    to_visit: List[str] = [url]
    priority_queue: List[str] = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    # Titles that actually appear on Indian SMB sites. The old list missed
    # MD, Principal (e.g. "Principal Dentist" - the dental norm), General
    # Manager, Promoter and Chairman, which together cover the majority of
    # owner-operator titles in the target market.
    EXEC_TITLES = [
        r'founder', r'co-founder', r'ceo', r'chief executive officer',
        r'managing director', r'md', r'director', r'principal(?:\s+\w+)?',
        r'general manager', r'manager', r'promoter', r'chairman',
        r'chairperson', r'president', r'owner', r'partner', r'proprietor',
        r'administrator', r'head of \w+', r'vice president', r'vp',
    ]
    TITLE_PATTERN = re.compile(
        # The separator class now includes the em-dash (U+2014), en-dash
        # (U+2013) and bullet (U+2022) - all three are used by Indian SMB
        # sites and all three were silently failing to split name from title.
        r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,2})\s*'
        r'(?:[-\u2013\u2014\u2022|,;:()]|\bis\b|\bas\b|&)\s*('
        + '|'.join(EXEC_TITLES) + r')\b',
        re.IGNORECASE
    )

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, verify=False, headers=headers) as client:
        while (priority_queue or to_visit) and len(visited) < max_pages:
            current_url = priority_queue.pop(0) if priority_queue else to_visit.pop(0)
            
            clean_curr = current_url.split("#")[0].rstrip("/")
            if clean_curr in visited:
                continue
            visited.add(clean_curr)

            try:
                response = await client.get(current_url)
                if response.status_code != 200:
                    continue

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                html_text = response.text

                # 1. Regex email search + deobfuscated text search
                normalized_text = deobfuscate_text_emails(html_text)
                raw_emails = EMAIL_REGEX.findall(normalized_text)
                for em in raw_emails:
                    em_clean = em.lower().strip(".")
                    if not any(em_clean.endswith(ext) for ext in EXCLUDED_EMAIL_EXTENSIONS):
                        domain = em_clean.split("@")[-1] if "@" in em_clean else ""
                        if domain and not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
                            emails.add(em_clean)

                # 2. Regex phone search
                raw_phones = PHONE_REGEX.findall(html_text)
                for ph in raw_phones:
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

                # Executive detection on about/team pages
                text_clean = soup.get_text(" ", strip=True)
                for match in TITLE_PATTERN.finditer(text_clean):
                    found_name, found_title = match.group(1).strip(), match.group(2).strip()
                    if not _is_plausible_person_name(found_name):
                        continue
                    executives.append({"name": found_name, "title": found_title.title()})
                
                for link in soup.find_all('a', href=True):
                    href = link['href'].strip()

                    # Mailto links
                    if href.lower().startswith('mailto:'):
                        em = href.split('mailto:')[1].split('?')[0].strip()
                        if EMAIL_REGEX.match(em):
                            em_clean = em.lower()
                            domain = em_clean.split("@")[-1]
                            if not any(ex in domain for ex in EXCLUDED_EMAIL_DOMAINS):
                                emails.add(em_clean)

                    # Tel links
                    elif href.lower().startswith('tel:'):
                        ph = href.split('tel:')[1].split('?')[0].strip()
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
                    elif 'twitter.com' in href or 'x.com' in href:
                        socials['twitter'] = href
                    elif 'youtube.com' in href:
                        socials['youtube'] = href

                    # Internal page discovery
                    else:
                        full_next = urljoin(current_url, href)
                        next_parsed = urlparse(full_next)
                        next_domain = next_parsed.netloc.lower().replace("www.", "")

                        if next_domain == base_domain:
                            path_lower = next_parsed.path.lower()
                            if any(kw in path_lower for kw in CONTACT_PRIORITY_KEYWORDS):
                                if full_next not in visited and full_next not in priority_queue:
                                    priority_queue.append(full_next)
                            else:
                                if full_next not in visited and full_next not in to_visit and len(to_visit) < 10:
                                    to_visit.append(full_next)

            except Exception as e:
                logger.debug(f"Error crawling {current_url}: {e}")
                continue

    return {
        "emails": list(emails),
        "phones": list(phones),
        "whatsapp": list(whatsapp_links)[0] if whatsapp_links else None,
        "socials": socials,
        "executives": executives[:5]
    }


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
        crawl_res: Dict[str, Any] = {}
        if business.website:
            try:
                crawl_res = await crawl_website_for_contacts(business.website)
                for em in crawl_res.get("emails", []):
                    all_emails.add(em)
                for ph in crawl_res.get("phones", []):
                    all_phones.add(ph)
                if crawl_res.get("whatsapp"):
                    discovered_whatsapp = crawl_res.get("whatsapp")
                if crawl_res.get("socials"):
                    discovered_socials.update(crawl_res.get("socials"))
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

            merged_socials = await find_business_socials(business, contact_socials=discovered_socials)
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
        for email in all_emails:
            stmt = select(Contact).where(Contact.business_id == business.id, Contact.email == email)
            res = await db.execute(stmt)
            existing_contact = res.scalars().first()

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
            execs = crawl_res.get("executives", []) if business.website else []

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
                if discovered_socials:
                    existing_contact.social_links = discovered_socials
                if discovered_whatsapp and not existing_contact.whatsapp_link:
                    existing_contact.whatsapp_link = discovered_whatsapp

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
                c = Contact(
                    business_id=business.id,
                    first_name=business.name.split()[0] if business.name else "Owner",
                    phone=in_phone.to_e164(business.phone) or business.phone,
                    whatsapp_link=in_phone.whatsapp_link(business.phone),
                    preferred_channel=in_phone.preferred_channel(business.phone),
                    extra_data={
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
                from app.qualifier.signals import probe_business_health
                health_patch = await probe_business_health(business)
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
    """
    count = 0
    async with async_session_maker() as db:
        stmt = select(Business).order_by(Business.id.desc()).limit(limit)
        res = await db.execute(stmt)
        businesses = res.scalars().all()

        for b in businesses:
            try:
                await enrich_business_by_id(b.id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to enrich business {b.id}: {e}")

    return count
