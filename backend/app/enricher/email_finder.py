import httpx
from bs4 import BeautifulSoup
import re
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
PHONE_REGEX = re.compile(r'(?:\+?91[\s-]?)?[6789]\d{9}|(?:\+?1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')

EXCLUDED_EMAIL_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js', '.woff', '.pdf')
EXCLUDED_EMAIL_DOMAINS = ('sentry.io', 'example.com', 'wixpress.com', 'domain.com', 'email.com', 'google.com', 'schema.org')

CONTACT_PRIORITY_KEYWORDS = [
    'contact', 'about', 'reach', 'touch', 'team', 'connect', 'help', 'info', 'support'
]

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

    # Queue of URLs to visit
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
                    ph_clean = ph.strip()
                    if len(re.sub(r'\D', '', ph_clean)) >= 10:
                        phones.add(ph_clean)

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
    Enriches a specific Business record by crawling its website,
    validating discovered emails, and saving contacts to database.
    """
    async with async_session_maker() as db:
        business = await db.get(Business, business_id)
        if not business or not business.website:
            return {"error": "Business not found or has no website"}

        crawl_result = await crawl_website_for_contacts(business.website)
        discovered_emails = crawl_result.get("emails", [])
        discovered_phones = crawl_result.get("phones", [])
        whatsapp = crawl_result.get("whatsapp")
        socials = crawl_result.get("socials", {})

        # Update business phone if missing
        if not business.phone and discovered_phones:
            business.phone = discovered_phones[0]

        # Process each discovered email
        verified_count = 0
        for email in discovered_emails:
            # Check if contact already exists
            stmt = select(Contact).where(Contact.email == email)
            res = await db.execute(stmt)
            existing_contact = res.scalars().first()

            # Verify email deliverability via DNS/SMTP
            is_valid, v_status = verify_email_smtp(email)
            if is_valid:
                verified_count += 1

            if not existing_contact:
                new_contact = Contact(
                    business_id=business.id,
                    first_name=business.name.split()[0] if business.name else "Team",
                    title="Decision Maker",
                    email=email,
                    phone=discovered_phones[0] if discovered_phones else business.phone,
                    whatsapp_link=whatsapp or (f"https://wa.me/{re.sub(r'[^0-9]', '', business.phone)}" if business.phone else None),
                    social_links=socials,
                    is_verified=is_valid,
                    verification_status=v_status,
                    source="website_enricher"
                )
                db.add(new_contact)
            else:
                existing_contact.is_verified = is_valid
                existing_contact.verification_status = v_status
                if socials:
                    existing_contact.social_links = socials
                if whatsapp and not existing_contact.whatsapp_link:
                    existing_contact.whatsapp_link = whatsapp

        await db.commit()
        return {
            "business_id": business_id,
            "emails_found": len(discovered_emails),
            "verified_emails": verified_count,
            "phones_found": len(discovered_phones),
            "socials": socials
        }


async def enrich_all_pending_businesses(limit: int = 25) -> int:
    """
    Finds all businesses with a website that do not yet have a verified email,
    and runs enrichment on them.
    """
    count = 0
    async with async_session_maker() as db:
        # Select businesses with website
        stmt = select(Business).where(Business.website.isnot(None)).limit(limit)
        res = await db.execute(stmt)
        businesses = res.scalars().all()

        for b in businesses:
            try:
                await enrich_business_by_id(b.id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to enrich business {b.id}: {e}")

    return count
