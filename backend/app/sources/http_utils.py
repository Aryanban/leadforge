import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
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


async def fetch_html(url: str, timeout: float = 15.0) -> Optional[str]:
    """Best-effort HTML fetch. Never raises; returns None on any failure."""
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, verify=False, headers=headers
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.debug(f"fetch_html {url} -> HTTP {response.status_code}")
                return None
            return response.text
    except Exception as e:
        logger.debug(f"fetch_html {url} failed: {e}")
        return None


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
