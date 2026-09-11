import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse
from urllib.parse import urlparse, urljoin
import logging
from typing import Dict, List, Set, Any, Optional
from sqlalchemy import select

from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.verifier.smtp_verifier import verify_email_smtp

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6789]\d{9}|0?[6789]\d{4}\s*\d{5}|0?[6789]\d{9}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})')

EXCLUDED_EMAIL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.woff', '.pdf')
EXCLUDED_EMAIL_DOMAINS = ('sentry.io', 'example.com', 'wixpress.com', 'domain.com', 'email.com', 'google.com', 'schema.org')

CONTACT_PRIORITY_KEYWORDS = [
    'contact', 'about', 'reach', 'touch', 'team', 'connect', 'help', 'info', 'support'
]


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

    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc.lower().replace("www.", "")

    to_visit: List[str] = [url]
    priority_queue: List[str] = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

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

                # 1. Regex email search
                raw_emails = EMAIL_REGEX.findall(html_text)
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

                # 3. DOM parsing for mailto:, tel:, WhatsApp, and Socials
                soup = BeautifulSoup(html_text, 'html.parser')
                
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
        "socials": socials
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

        # Update business phone if missing
        if not business.phone and all_phones:
            business.phone = list(all_phones)[0]

        # Step 3: Process and verify each discovered email
        verified_count = 0
        for email in all_emails:
            stmt = select(Contact).where(Contact.business_id == business.id, Contact.email == email)
            res = await db.execute(stmt)
            existing_contact = res.scalars().first()

            is_valid, v_status = verify_email_smtp(email)
            if is_valid:
                verified_count += 1

            clean_phone = re.sub(r'[^0-9]', '', business.phone or (list(all_phones)[0] if all_phones else ""))
            if not existing_contact:
                new_contact = Contact(
                    business_id=business.id,
                    first_name=business.name.split()[0] if business.name else "Owner",
                    title="Owner / Decision Maker",
                    email=email,
                    phone=business.phone or (list(all_phones)[0] if all_phones else None),
                    whatsapp_link=discovered_whatsapp or (f"https://wa.me/{clean_phone}" if clean_phone else None),
                    social_links=discovered_socials,
                    is_verified=is_valid,
                    verification_status=v_status,
                    source="multi_source_enricher"
                )
                db.add(new_contact)
            else:
                existing_contact.is_verified = is_valid
                existing_contact.verification_status = v_status
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
                    existing_contact.phone = list(all_phones)[0]
                    clean_phone = re.sub(r'[^0-9]', '', existing_contact.phone or "")
                    existing_contact.whatsapp_link = f"https://wa.me/{clean_phone}" if clean_phone else None
            elif business.phone:
                clean_phone = re.sub(r'[^0-9]', '', business.phone or "")
                c = Contact(
                    business_id=business.id,
                    first_name=business.name.split()[0] if business.name else "Owner",
                    phone=business.phone,
                    whatsapp_link=f"https://wa.me/{clean_phone}" if clean_phone else None,
                    source="multi_source_enricher",
                    verification_status="unverified"
                )
                db.add(c)

        await db.commit()
        return {
            "business_id": business_id,
            "name": business.name,
            "emails_found": len(all_emails),
            "verified_emails": verified_count,
            "phones_found": len(all_phones),
            "website": business.website,
            "socials": discovered_socials
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
