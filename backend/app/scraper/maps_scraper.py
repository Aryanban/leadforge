import re
import urllib.parse
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select

from app.scraper.anti_detect import get_random_user_agent, get_random_viewport, random_delay
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r'(?:\+?91[\s-]?)?[6789]\d{9}|(?:\+?1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}')

async def scrape_google_maps_playwright(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    High-fidelity Google Maps scraping via Playwright headless Chromium.
    Scrolls through feed, inspects cards, extracts detailed metadata.
    """
    from playwright.async_api import async_playwright
    results: List[Dict[str, Any]] = []
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/maps/search/{encoded_query}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport=get_random_viewport(),
            locale="en-US"
        )
        page = await context.new_page()

        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await random_delay(1500, 2500)

            # Accept cookies/consent dialog if present
            try:
                consent_btn = await page.query_selector('button[aria-label*="Accept all"], form[action*="consent"] button')
                if consent_btn:
                    await consent_btn.click()
                    await random_delay(800, 1500)
            except Exception:
                pass

            # Wait for search results feed or place container
            try:
                await page.wait_for_selector('div[role="feed"], div.m6QErb', timeout=12000)
            except Exception:
                logger.warning(f"Could not find feed selector for query '{query}', continuing with fallback selectors")

            scroll_attempts = 0
            max_scrolls = max(5, (max_results // 4) + 3)

            while len(results) < max_results and scroll_attempts < max_scrolls:
                place_links = await page.query_selector_all('a[href*="/maps/place/"]')
                if not place_links:
                    break

                for i in range(len(results), min(len(place_links), max_results)):
                    link = place_links[i]
                    try:
                        href = await link.get_attribute("href") or ""
                        aria_label = await link.get_attribute("aria-label") or ""
                        
                        # Extract coordinates if present in URL
                        lat, lng = None, None
                        coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', href)
                        if coord_match:
                            lat = float(coord_match.group(1))
                            lng = float(coord_match.group(2))

                        # Click into item for full panel details
                        await link.scroll_into_view_if_needed()
                        await link.click()
                        await random_delay(800, 1500)

                        # Extract name
                        name = aria_label
                        if not name:
                            h1_el = await page.query_selector('h1.DUwDvf, div.fontHeadlineLarge')
                            if h1_el:
                                name = (await h1_el.inner_text()).strip()

                        if not name:
                            continue

                        # Extract website
                        website = ""
                        try:
                            web_el = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Website"]')
                            if web_el:
                                website = await web_el.get_attribute("href") or ""
                        except Exception:
                            pass

                        # Extract phone
                        phone = ""
                        try:
                            phone_el = await page.query_selector('button[data-item-id*="phone:"], button[aria-label*="Phone"]')
                            if phone_el:
                                phone_aria = await phone_el.get_attribute("aria-label") or ""
                                phone = phone_aria.replace("Phone number: ", "").replace("Phone: ", "").strip()
                        except Exception:
                            pass

                        # Extract address
                        address = ""
                        try:
                            addr_el = await page.query_selector('button[data-item-id*="address"], button[aria-label*="Address"]')
                            if addr_el:
                                addr_aria = await addr_el.get_attribute("aria-label") or ""
                                address = addr_aria.replace("Address: ", "").strip()
                        except Exception:
                            pass

                        # Extract rating and review count
                        rating, reviews_count = None, None
                        try:
                            rating_el = await page.query_selector('span[role="img"][aria-label*="stars"], div.F7nice span')
                            if rating_el:
                                rating_text = await rating_el.inner_text()
                                r_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
                                if r_match:
                                    rating = float(r_match.group(1))
                            
                            rev_el = await page.query_selector('span[aria-label*="reviews"], span.fontBodyMedium > span')
                            if rev_el:
                                rev_text = await rev_el.inner_text()
                                num_match = re.search(r'\(?([\d,]+)\)?', rev_text)
                                if num_match:
                                    reviews_count = int(num_match.group(1).replace(",", ""))
                        except Exception:
                            pass

                        # Extract category/industry
                        industry = ""
                        try:
                            cat_el = await page.query_selector('button.DkEaL, div.fontBodyMedium span')
                            if cat_el:
                                industry = (await cat_el.inner_text()).strip()
                        except Exception:
                            pass

                        results.append({
                            "name": name,
                            "place_id": href.split("?")[0][-60:] if href else None,
                            "website": website,
                            "phone": phone,
                            "address": address,
                            "rating": rating,
                            "reviews_count": reviews_count,
                            "industry": industry,
                            "latitude": lat,
                            "longitude": lng,
                            "source": "playwright_maps",
                            "query": query
                        })

                        if len(results) >= max_results:
                            break

                    except Exception as e:
                        logger.warning(f"Error parsing map card {i}: {e}")
                        continue

                # Scroll down feed
                feed = await page.query_selector('div[role="feed"]')
                if feed and len(results) < max_results:
                    await feed.hover()
                    await page.mouse.wheel(0, 7000)
                    await random_delay(1500, 2500)
                    scroll_attempts += 1
                else:
                    break

        except Exception as e:
            logger.error(f"Playwright scraping encountered error: {e}")
        finally:
            await browser.close()

    return results


async def scrape_google_http_fallback(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Fast HTTP-based scraper that queries Google local search HTML.
    Does not require Playwright/Chromium and works on any lightweight environment.
    """
    import httpx
    from bs4 import BeautifulSoup

    results: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Query Google local search
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={encoded_query}&tbm=lcl&hl=en"

    try:
        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # Google local listing cards often have class 'VkpGBb', 'rllt__details', or data-cid
                cards = soup.select('div.VkpGBb, div.rllt__details, div[data-cid]')
                if not cards:
                    cards = soup.select('div.u9t22c, div.cXedhc')

                for card in cards[:max_results]:
                    name_el = card.select_one('div.dbg0pd, span.OSrXXb, div.fontHeadlineSmall')
                    name = name_el.get_text(strip=True) if name_el else ""
                    if not name:
                        continue

                    # Text info
                    text_blob = card.get_text(" | ", strip=True)

                    # Phone match
                    phones = PHONE_REGEX.findall(text_blob)
                    phone = phones[0] if phones else ""

                    # Website
                    website = ""
                    for link in card.select('a[href]'):
                        href = link.get("href", "")
                        if "url?q=" in href:
                            clean_url = href.split("url?q=")[1].split("&")[0]
                            if not any(x in clean_url for x in ["google.com", "maps.google", "search"]):
                                website = urllib.parse.unquote(clean_url)
                                break
                        elif href.startswith("http") and not any(x in href for x in ["google.com", "gstatic"]):
                            website = href
                            break

                    # Rating
                    rating = None
                    rating_el = card.select_one('span.yi40Hd, span.z3HNkc')
                    if rating_el:
                        try:
                            rating = float(rating_el.get_text(strip=True))
                        except Exception:
                            pass

                    results.append({
                        "name": name,
                        "website": website,
                        "phone": phone,
                        "address": text_blob[:120],
                        "rating": rating,
                        "reviews_count": None,
                        "industry": query.split(" in ")[0] if " in " in query else "Local Business",
                        "source": "http_search",
                        "query": query
                    })

    except Exception as e:
        logger.error(f"HTTP fallback scraper error: {e}")

    return results


async def scrape_leads_and_save(job_id: int, query: str, max_results: int = 20) -> int:
    """
    Main orchestrator for scraping:
    1. Tries Playwright headless browser first
    2. Falls back to HTTP scraper if Playwright is unavailable
    3. Persists results directly into SQLite/Postgres database
    4. Creates initial contact records for each business
    5. Updates ScrapeJob status
    """
    raw_leads = []
    error_msg = None

    # Step 1: Attempt Playwright
    try:
        raw_leads = await scrape_google_maps_playwright(query, max_results)
    except Exception as e:
        logger.warning(f"Playwright unavailable or failed ({e}), falling back to HTTP scraper")
        error_msg = str(e)

    # Step 2: Fallback if Playwright returned 0 or errored
    if not raw_leads:
        try:
            raw_leads = await scrape_google_http_fallback(query, max_results)
        except Exception as e:
            logger.error(f"HTTP scraper fallback also failed: {e}")
            error_msg = f"Playwright: {error_msg}; HTTP: {e}"

    # Step 3: Persist into database with deduplication
    saved_count = 0
    async with async_session_maker() as db:
        try:
            # Update job to running
            job = await db.get(ScrapeJob, job_id)
            if job:
                job.status = "running"
                await db.commit()

            for lead in raw_leads:
                name = lead.get("name", "").strip()
                if not name:
                    continue

                # Check for existing business by name + phone or website
                stmt = select(Business).where(Business.name == name)
                res = await db.execute(stmt)
                existing = res.scalars().first()

                if not existing:
                    business = Business(
                        place_id=lead.get("place_id"),
                        name=name,
                        website=lead.get("website") or None,
                        phone=lead.get("phone") or None,
                        address=lead.get("address") or None,
                        rating=lead.get("rating"),
                        reviews_count=lead.get("reviews_count"),
                        industry=lead.get("industry") or lead.get("query"),
                        latitude=lead.get("latitude"),
                        longitude=lead.get("longitude"),
                        extra_data={"query": query, "scraped_at": datetime.utcnow().isoformat()}
                    )
                    db.add(business)
                    await db.flush()

                    # Create initial contact entry
                    contact = Contact(
                        business_id=business.id,
                        first_name=name.split()[0] if len(name.split()) > 0 else "Contact",
                        title="Owner / Decision Maker",
                        phone=lead.get("phone") or None,
                        whatsapp_link=f"https://wa.me/{re.sub(r'[^0-9]', '', lead.get('phone'))}" if lead.get("phone") else None,
                        email=None,
                        source="google_maps",
                        verification_status="unverified"
                    )
                    db.add(contact)
                    saved_count += 1
                else:
                    # Update phone or website if previously missing
                    if not existing.phone and lead.get("phone"):
                        existing.phone = lead.get("phone")
                    if not existing.website and lead.get("website"):
                        existing.website = lead.get("website")

            # Finalize ScrapeJob
            if job:
                job.status = "completed" if saved_count > 0 or len(raw_leads) > 0 else "completed"
                job.total_found = len(raw_leads)
                job.leads_saved = saved_count
                job.finished_at = datetime.utcnow()
                if error_msg and saved_count == 0:
                    job.error = error_msg
            await db.commit()

        except Exception as e:
            logger.error(f"Error persisting scrape results: {e}")
            if job:
                job.status = "failed"
                job.error = str(e)
                await db.commit()

    return saved_count
