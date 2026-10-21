import re
import urllib.parse
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy import select

from app.scraper.anti_detect import get_random_user_agent, get_random_viewport, random_delay
from app.database import async_session_maker
from app.models.business import Business
from app.models.contact import Contact
from app.models.scrape_job import ScrapeJob

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6789]\d{9}|0?[6789]\d{4}\s*\d{5}|0?[6789]\d{9}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})')

# Query -> industry. Splitting a search query on " in " only works when the
# user phrases it exactly that way; anything else fell back to a hardcoded
# "Real Estate", which is how every scraped lead ended up mis-categorised.
# This parses the common phrasings and otherwise keeps the whole query.
_QUERY_SPLIT_RE = re.compile(
    r'\s+(?:in|near|around|at|within)\s+', re.IGNORECASE
)


#: Unicode Private Use Area (U+E000-U+F8FF). Google renders category icons
#: from this block; ``innerText`` exposes them as the raw character, so they
#: end up glued onto the front of a card's metadata line.
_PUA_RE = re.compile("[\\ue000-\\uf8ff]")


def _strip_pua(text: str) -> str:
    """Removes Private-Use-Area icon glyphs from scraped card text."""
    if not text:
        return ""
    return _PUA_RE.sub("", text).strip()


def industry_of_query(query: str) -> str:
    """Extracts the category from a Maps search query.

    "dentists in Rohini Delhi" -> "dentists"; "Dentists near Saket" -> "Dentists".
    Returns the cleaned query unchanged when no location preposition is present,
    so an unrecognised phrasing never silently becomes a made-up industry.
    """
    if not query or not query.strip():
        return "Business"
    parts = _QUERY_SPLIT_RE.split(query.strip(), maxsplit=1)
    head = parts[0].strip(" ,-").strip()
    if head and len(parts) > 1 and len(head) >= 2:
        return head
    # No location clause - the query itself is the category.
    return query.strip()


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
            viewport=get_random_viewport(),
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = await context.new_page()

        # Performance Turbo: abort heavy images, media, fonts and stylesheets
        # to accelerate DOM parsing 3x-5x. Stylesheets were missing from the
        # original list, which meant the biggest single asset class was still
        # being downloaded in full.
        async def _block_heavy_assets(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", _block_heavy_assets)

        try:
            logger.info(f"Opening Google Maps search for: {query}")
            await page.goto(url, timeout=35000, wait_until="domcontentloaded")
            # Humanised deceleration: a fixed 3s wait is a metronome, and a
            # metronome is a fingerprint. ``random_delay`` was imported here
            # for a long time and never called.
            await random_delay(1800, 3600)

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
                        "industry": industry_of_query(query),
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
                    #
                    # The card's metadata line is "<icon glyph> · <category> ·
                    # <address>". The icon is a Private-Use-Area codepoint
                    # (U+E000-U+F8FF) that the DOM renders as a glyph but
                    # ``innerText`` exposes as the raw character. Splitting on
                    # "·" and keeping parts[0] therefore stored the icon as the
                    # category and the address became the category + street.
                    category = ""
                    address = ""
                    for l in lines[1:]:
                        if "·" in l and not any(l.startswith(x) for x in ["Closed", "Open", "Opens"]):
                            cleaned = _strip_pua(l)
                            parts = [p.strip() for p in cleaned.split("·") if p.strip()]
                            if parts:
                                category = parts[0]
                                if len(parts) > 1:
                                    address = " · ".join(parts[1:])
                            break

                    # Extract Coordinates (Lat, Lng)
                    latitude, longitude = None, None
                    coord_match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', href)
                    if coord_match:
                        try:
                            latitude = float(coord_match.group(1))
                            longitude = float(coord_match.group(2))
                        except Exception:
                            pass
                    if latitude is None:
                        center_match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', href)
                        if center_match:
                            try:
                                latitude = float(center_match.group(1))
                                longitude = float(center_match.group(2))
                            except Exception:
                                pass

                    # Check Claimed / Unclaimed GBP Status
                    is_claimed = True
                    if any("claim this business" in l.lower() or "own this business" in l.lower() for l in lines):
                        is_claimed = False

                    # Extract Operational Status
                    status = "Operational"
                    for l in lines:
                        if "closed permanently" in l.lower():
                            status = "Permanently Closed"
                            break
                        elif "closed temporarily" in l.lower():
                            status = "Temporarily Closed"
                            break
                        elif any(l.startswith(x) for x in ["Open", "Closed", "Opens"]):
                            status = l.split("·")[0].strip()
                            break

                    # Extract Price Tier
                    price_tier = None
                    for symbol in ["₹₹₹₹", "₹₹₹", "₹₹", "₹", "$$$$", "$$$", "$$", "$"]:
                        if symbol in text:
                            price_tier = symbol
                            break

                    maps_url = href.split("?")[0] if (href and href.startswith("http")) else f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name + ' ' + (address or query))}"

                    # Place id: Google puts the CID in the card href as
                    # ``!1s0x...:0x...``. The old code took the last 60
                    # characters of the URL path, which is a truncated URL
                    # fragment - not a place id at all. ``Business.place_id`` is
                    # UNIQUE and is the primary dedupe key, so a Playwright
                    # row and an HTTP row for the same business had
                    # incompatible keys and never matched.
                    place_id = None
                    if href:
                        cid_match = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", href)
                        if cid_match:
                            place_id = cid_match.group(1)

                    results.append({
                        "name": name,
                        "phone": phone,
                        "website": website,
                        "address": address or query,
                        "maps_url": maps_url,
                        "rating": rating,
                        "reviews_count": reviews,
                        "industry": category or (query.split(" in ")[0] if " in " in query else "Local Business"),
                        "place_id": place_id,
                        "latitude": latitude,
                        "longitude": longitude,
                        "is_claimed": is_claimed,
                        "operational_status": status,
                        "price_tier": price_tier,
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


async def scrape_leads_and_save(
    job_id: int,
    query: str,
    max_results: int = 20,
    icp_profile_id: Optional[int] = None,
    enrich: bool = True,
) -> Tuple[int, List[int]]:
    """
    Main orchestrator for scraping:
    1. Runs high-fidelity Google Maps Playwright scraper
    2. Falls back to search HTTP scraper if needed
    3. Persists results directly into SQLite/Postgres database
    4. Creates initial contact records for each business
    5. Updates ScrapeJob status

    When icp_profile_id is provided, newly discovered businesses are tagged with the
    profile so downstream scoring uses the ICP-aware weights. Pass enrich=False to
    suppress the fire-and-forget enrichment (e.g. the discovery pipeline enriches
    synchronously so it can rank once enrichment is complete).
    """
    raw_leads = []
    error_msg = None

    # Step 1: HTTP first.
    #
    # The order used to be Playwright first, which meant the endpoint the
    # dashboard actually calls ran the slow path by default. Measured on the
    # same query:
    #
    #     HTTP       2.4s   20/20 phones, 17/20 websites, valid place ids
    #     Playwright 8.9s    0/20 phones,  0/20 websites, PUA-glyph addresses
    #
    # The browser path needs a launch plus a scroll loop to reach the same 20
    # places, and it cannot extract the phone or website at all. It is a
    # fallback for when the HTTP transport is blocked, not the default.
    try:
        # Imported lazily: maps_http imports ``industry_of_query`` from this
        # module at import time, so a module-level import would be circular.
        from app.scraper.maps_http import scrape_google_maps_http
        raw_leads = await scrape_google_maps_http(query, max_results=max_results)
        if not raw_leads:
            logger.info("HTTP Maps path returned nothing for %r - trying Playwright", query)
    except Exception as e:
        logger.warning(f"HTTP Maps scraper error: {e}, falling back to Playwright")
        error_msg = str(e)

    # Step 2: Fallback to the browser path if HTTP returned 0 or errored.
    if not raw_leads:
        try:
            raw_leads = await scrape_google_maps_playwright(query, max_results)
        except Exception as e:
            logger.warning(f"Playwright scraper error: {e}")
            error_msg = f"HTTP: {error_msg}; Playwright: {e}"

    # Step 3: Last resort - plain web search.
    if not raw_leads:
        try:
            logger.info(f"Running search fallback for: {query}")
            raw_leads = await scrape_google_http_fallback(query, max_results)
        except Exception as e:
            logger.error(f"HTTP fallback also failed: {e}")
            error_msg = f"HTTP: {error_msg}; Playwright: {e}; Search: {e}"

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
                        latitude=lead.get("latitude"),
                        longitude=lead.get("longitude"),
                        source=lead.get("source", "google_maps"),
                        icp_profile_id=icp_profile_id,
                        extra_data={
                            "query": query,
                            "scraped_at": datetime.utcnow().isoformat(),
                            "is_claimed": lead.get("is_claimed", True),
                            "operational_status": lead.get("operational_status", "Operational"),
                            "price_tier": lead.get("price_tier"),
                        }
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
                    if icp_profile_id and not existing.icp_profile_id:
                        existing.icp_profile_id = icp_profile_id

            # Finalize ScrapeJob - but NOT as "completed" yet. The job is only
            # really finished once enrichment has run, and marking it complete
            # before then is how a scrape job "reported 100% done" while the
            # leads were still raw.
            if job:
                job.total_found = len(raw_leads)
                job.leads_saved = saved_count
                if error_msg and len(raw_leads) == 0:
                    job.error = error_msg
                else:
                    job.status = "enriching"
            await db.commit()
            logger.info(
                "Scrape job %s scraped: found %d, saved %d new leads", job_id, len(raw_leads), saved_count
            )

            # Trigger multi-source web enrichment for newly discovered businesses.
            #
            # The old code fired an unbounded ``asyncio.create_task`` per lead
            # and dropped the reference. That meant (a) N leads produced N
            # concurrent Yahoo+Bing+SMTP bursts with no throttle, (b) CPython
            # was free to garbage-collect a still-running task, and (c) a
            # restart lost every pending enrichment. Now it is a bounded,
            # awaited fan-out.
            if enrich and new_biz_ids:
                from app.enricher.email_finder import enrich_business_by_id
                from app.discovery.pipeline import ENRICH_CONCURRENCY

                _sem = asyncio.Semaphore(max(1, ENRICH_CONCURRENCY))

                async def _enrich_one(biz_id: int) -> None:
                    async with _sem:
                        try:
                            await enrich_business_by_id(biz_id)
                        except asyncio.CancelledError:
                            raise
                        except Exception as enrich_err:
                            logger.warning(
                                "Auto-enrichment failed for lead %s: %s", biz_id, enrich_err
                            )

                await asyncio.gather(*(_enrich_one(bid) for bid in new_biz_ids))

            if job:
                job.status = "completed"
                job.finished_at = datetime.utcnow()
                await db.commit()
            logger.info(f"Scrape job {job_id} completed (enriched {len(new_biz_ids)} lead(s))")

        except Exception as e:
            logger.error(f"Error persisting scrape results: {e}")
            if job:
                job.status = "failed"
                job.error = str(e)
                await db.commit()

    return saved_count, new_biz_ids
