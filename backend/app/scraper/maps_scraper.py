import re
import urllib.parse
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select

from app.scraper.anti_detect import get_random_user_agent, get_random_viewport, random_delay
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6789]\d{9}|0?[6789]\d{4}\s*\d{5}|0?[6789]\d{9}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})')

async def _launch_browser(p):
    """
    Launch browser with multi-channel fallback:
    1. Native Chrome (Apple Silicon / Linux / Windows native, zero segfaults)
    2. Default Chromium
    3. Microsoft Edge
    4. Firefox
    """
    # 1. Native Chrome
    try:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-setuid-sandbox"]
        )
        return browser
    except Exception as e:
        logger.debug(f"Native Chrome launch skipped: {e}")

    # 2. Standard Chromium
    try:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-setuid-sandbox"]
        )
        return browser
    except Exception as e:
        logger.debug(f"Standard Chromium launch skipped: {e}")

    # 3. Microsoft Edge
    try:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        return browser
    except Exception as e:
        logger.debug(f"Edge launch skipped: {e}")

    # 4. Firefox fallback
    try:
        browser = await p.firefox.launch(headless=True)
        return browser
    except Exception as e:
        logger.warning(f"Firefox launch skipped: {e}")

    raise RuntimeError("No compatible Playwright browser could be launched.")


async def scrape_google_maps_playwright(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    High-fidelity Google Maps scraping via Playwright.
    Scrolls through search results feed and extracts structured business data.
    """
    from playwright.async_api import async_playwright
    results: List[Dict[str, Any]] = []
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.google.com/maps/search/{encoded_query}"

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        context = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1280, "height": 900},
            locale="en-US"
        )
        page = await context.new_page()

        try:
            logger.info(f"Opening Google Maps search for: {query}")
            await page.goto(url, timeout=35000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Accept consent/cookies if present
            try:
                consent_btn = await page.query_selector('button[aria-label*="Accept all"], form[action*="consent"] button, button[aria-label*="Agree"]')
                if consent_btn:
                    await consent_btn.click()
                    await asyncio.sleep(1.5)
            except Exception:
                pass

            # Check if this is a direct single business details view instead of a feed
            h1_el = await page.query_selector('h1.DUwDvf')
            if h1_el and not await page.query_selector('div.Nv2PK'):
                name = (await h1_el.inner_text()).strip()
                if name:
                    website = ""
                    try:
                        web_el = await page.query_selector('a[data-item-id="authority"], a[aria-label*="Website"]')
                        if web_el:
                            website = await web_el.get_attribute("href") or ""
                    except Exception:
                        pass

                    phone = ""
                    try:
                        phone_el = await page.query_selector('button[data-item-id*="phone:"], button[aria-label*="Phone"]')
                        if phone_el:
                            p_aria = await phone_el.get_attribute("aria-label") or ""
                            phone = p_aria.replace("Phone number: ", "").replace("Phone: ", "").strip()
                    except Exception:
                        pass

                    address = ""
                    try:
                        addr_el = await page.query_selector('button[data-item-id*="address"], button[aria-label*="Address"]')
                        if addr_el:
                            a_aria = await addr_el.get_attribute("aria-label") or ""
                            address = a_aria.replace("Address: ", "").strip()
                    except Exception:
                        pass

                    rating = None
                    try:
                        r_el = await page.query_selector('div.F7nice span[aria-hidden="true"]')
                        if r_el:
                            rating = float((await r_el.inner_text()).strip())
                    except Exception:
                        pass

                    results.append({
                        "name": name,
                        "phone": phone,
                        "website": website,
                        "address": address or query,
                        "rating": rating,
                        "reviews_count": None,
                        "industry": query.split(" in ")[0] if " in " in query else "Real Estate",
                        "source": "playwright_single",
                        "query": query
                    })
                    return results

            # Scroll search results feed
            feed = await page.query_selector('div[role="feed"]')
            max_scrolls = max(4, (max_results // 5) + 3)
            scroll_count = 0

            while scroll_count < max_scrolls:
                cards = await page.query_selector_all('div.Nv2PK')
                if len(cards) >= max_results or not feed:
                    break
                await feed.evaluate("el => el.scrollBy(0, 3500)")
                await asyncio.sleep(1.5)
                scroll_count += 1

            cards = await page.query_selector_all('div.Nv2PK')
            logger.info(f"Discovered {len(cards)} Google Maps cards for '{query}'")

            seen_names = set()
            for card in cards[:max_results]:
                try:
                    text = await card.evaluate("el => el.innerText")
                    lines = [l.strip() for l in text.split("\n") if l.strip()]

                    # Extract Name
                    link_el = await card.query_selector('a[href*="/maps/place/"]')
                    href = await link_el.get_attribute("href") if link_el else ""
                    aria = await link_el.get_attribute("aria-label") if link_el else ""
                    name = aria or (lines[0] if lines else "")

                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)

                    # Extract Phone
                    phone = ""
                    phone_el = await card.query_selector('span.UsdlK')
                    if phone_el:
                        phone = (await phone_el.inner_text()).strip()
                    if not phone:
                        phone_match = PHONE_REGEX.search(text)
                        if phone_match:
                            phone = phone_match.group(1).strip()

                    # Extract Website
                    web_el = await card.query_selector('a[aria-label*="Website"], a[data-value="Website"], a[data-item-id="authority"]')
                    website = await web_el.get_attribute("href") if web_el else ""

                    # Extract Rating & Reviews
                    rating, reviews = None, None
                    r_el = await card.query_selector('span.MW4etd')
                    if r_el:
                        try:
                            rating = float((await r_el.inner_text()).strip())
                        except Exception:
                            pass
                    rev_match = re.search(r'\(([\d,]+)\)', text)
                    if rev_match:
                        try:
                            reviews = int(rev_match.group(1).replace(",", ""))
                        except Exception:
                            pass

                    # Extract Category & Address
                    category = ""
                    address = ""
                    for l in lines[1:]:
                        if "·" in l and not any(l.startswith(x) for x in ["Closed", "Open", "Opens"]):
                            parts = [p.strip() for p in l.split("·") if p.strip()]
                            if parts:
                                category = parts[0]
                                if len(parts) > 1:
                                    address = " · ".join(parts[1:])
                            break

                    maps_url = href.split("?")[0] if (href and href.startswith("http")) else f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name + ' ' + (address or query))}"

                    results.append({
                        "name": name,
                        "phone": phone,
                        "website": website,
                        "address": address or query,
                        "maps_url": maps_url,
                        "rating": rating,
                        "reviews_count": reviews,
                        "industry": category or (query.split(" in ")[0] if " in " in query else "Local Business"),
                        "place_id": href.split("?")[0][-60:] if href else None,
                        "source": "playwright_maps",
                        "query": query
                    })


                    if len(results) >= max_results:
                        break

                except Exception as card_err:
                    logger.warning(f"Error parsing card: {card_err}")
                    continue

        except Exception as e:
            logger.error(f"Playwright scraping encountered error: {e}")
            raise e
        finally:
            await browser.close()

    return results


async def scrape_google_http_fallback(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Reliable search HTTP fallback using DuckDuckGo HTML search.
    Guarantees that lead generation works even in environments without browser engines.
    """
    import httpx
    from bs4 import BeautifulSoup

    results: List[Dict[str, Any]] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query + ' phone contact website')}"

    try:
        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for r in soup.select("div.result__body")[:max_results]:
                    title_el = r.select_one("a.result__a")
                    snippet_el = r.select_one("a.result__snippet")
                    if not title_el:
                        continue

                    title = title_el.get_text(strip=True)
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    raw_link = title_el.get("href", "")

                    # Clean DuckDuckGo redirect URL
                    clean_website = ""
                    if "uddg=" in raw_link:
                        clean_website = urllib.parse.unquote(raw_link.split("uddg=")[1].split("&")[0])
                    elif raw_link.startswith("http"):
                        clean_website = raw_link

                    # Extract Phone from snippet/title
                    phone_match = PHONE_REGEX.search(snippet + " " + title)
                    phone = phone_match.group(1).strip() if phone_match else ""

                    clean_name = title.split(" - ")[0].split(" | ")[0].strip()
                    if clean_name:
                        results.append({
                            "name": clean_name,
                            "website": clean_website,
                            "phone": phone,
                            "address": snippet[:140] if snippet else query,
                            "rating": None,
                            "reviews_count": None,
                            "industry": query.split(" in ")[0] if " in " in query else "Local Business",
                            "source": "http_fallback",
                            "query": query
                        })

    except Exception as e:
        logger.error(f"HTTP fallback scraper error: {e}")

    return results


async def scrape_leads_and_save(job_id: int, query: str, max_results: int = 20) -> int:
    """
    Main orchestrator for scraping:
    1. Runs high-fidelity Google Maps Playwright scraper
    2. Falls back to search HTTP scraper if needed
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
        logger.warning(f"Playwright scraper error: {e}, falling back to HTTP scraper")
        error_msg = str(e)

    # Step 2: Fallback if Playwright returned 0 or errored
    if not raw_leads:
        try:
            logger.info(f"Running search fallback for: {query}")
            raw_leads = await scrape_google_http_fallback(query, max_results)
        except Exception as e:
            logger.error(f"HTTP fallback also failed: {e}")
            error_msg = f"Playwright: {error_msg}; HTTP: {e}"

    # Step 3: Persist into database with deduplication
    saved_count = 0
    async with async_session_maker() as db:
        try:
            job = await db.get(ScrapeJob, job_id)
            if job:
                job.status = "running"
                await db.commit()

            new_biz_ids = []
            for lead in raw_leads:
                name = lead.get("name", "").strip()
                if not name:
                    continue

                # Check for existing business by name
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
                        maps_url=lead.get("maps_url") or None,
                        rating=lead.get("rating"),
                        reviews_count=lead.get("reviews_count"),
                        industry=lead.get("industry") or lead.get("query"),
                        extra_data={"query": query, "scraped_at": datetime.utcnow().isoformat()}
                    )
                    db.add(business)
                    await db.flush()

                    # Create initial contact entry
                    clean_phone = re.sub(r'[^0-9]', '', lead.get("phone") or "")
                    contact = Contact(
                        business_id=business.id,
                        first_name=name.split()[0] if len(name.split()) > 0 else "Owner",
                        title="Owner / Decision Maker",
                        phone=lead.get("phone") or None,
                        whatsapp_link=f"https://wa.me/{clean_phone}" if clean_phone else None,
                        email=None,
                        source=lead.get("source", "google_maps"),
                        verification_status="unverified"
                    )
                    db.add(contact)
                    saved_count += 1
                    new_biz_ids.append(business.id)
                else:
                    # Update phone, website, or maps_url if missing
                    if not existing.phone and lead.get("phone"):
                        existing.phone = lead.get("phone")
                    if not existing.website and lead.get("website"):
                        existing.website = lead.get("website")
                    if not existing.maps_url and lead.get("maps_url"):
                        existing.maps_url = lead.get("maps_url")

            # Finalize ScrapeJob
            if job:
                job.status = "completed"
                job.total_found = len(raw_leads)
                job.leads_saved = saved_count
                job.finished_at = datetime.utcnow()
                if error_msg and len(raw_leads) == 0:
                    job.error = error_msg
            await db.commit()
            logger.info(f"Scrape job {job_id} completed: found {len(raw_leads)}, saved {saved_count} new leads")

            # Trigger multi-source web enrichment for newly discovered businesses in background
            if new_biz_ids:
                from app.enricher.email_finder import enrich_business_by_id
                for biz_id in new_biz_ids:
                    try:
                        asyncio.create_task(enrich_business_by_id(biz_id))
                    except Exception as enrich_err:
                        logger.warning(f"Error initiating auto-enrichment for lead {biz_id}: {enrich_err}")

        except Exception as e:
            logger.error(f"Error persisting scrape results: {e}")
            if job:
                job.status = "failed"
                job.error = str(e)
                await db.commit()

    return saved_count
