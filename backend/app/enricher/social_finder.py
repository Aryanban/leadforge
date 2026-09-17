import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.sources.http_utils import fetch_html

logger = logging.getLogger(__name__)

PLATFORM_HOSTS = {
    "linkedin": ("linkedin.com/company", "linkedin.com/in"),
    "facebook": ("facebook.com",),
    "instagram": ("instagram.com",),
    "twitter": ("twitter.com", "x.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "pinterest": ("pinterest.com",),
    "tiktok": ("tiktok.com",),
}

EXCLUDE_FRAGMENTS = ("sharer", "dialog", "share", "/p/", "search", "login", "help", "intent", "plugins", "tr:")


def _clean_url(href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip().split("?")[0].split("#")[0]
    if not href.startswith("http"):
        return None
    if any(fragment in href.lower() for fragment in EXCLUDE_FRAGMENTS):
        return None
    return href


def extract_socials_from_html(html: Optional[str]) -> Dict[str, str]:
    """
    Stage A social discovery: pulls profile links from anchor hrefs and from
    JSON-LD 'sameAs' structured data. Pure function, no network.
    """
    if not html:
        return {}

    found: Dict[str, str] = {}
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = _clean_url(link["href"])
        if not href:
            continue
        lowered = href.lower()
        for platform, hosts in PLATFORM_HOSTS.items():
            if any(host in lowered for host in hosts):
                if platform not in found:
                    found[platform] = href
                break

    # JSON-LD sameAs (schema.org) — the most reliable structured signal.
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except Exception:
            continue
        for node in _iter_jsonld(payload):
            same_as = node.get("sameAs") if isinstance(node, dict) else None
            if not isinstance(same_as, list):
                continue
            for entry in same_as:
                if not isinstance(entry, str):
                    continue
                url = _clean_url(entry)
                if not url:
                    continue
                lowered = url.lower()
                for platform, hosts in PLATFORM_HOSTS.items():
                    if any(host in lowered for host in hosts):
                        found.setdefault(platform, url)
                        break

    return found


def _iter_jsonld(payload: Any) -> List[Any]:
    """Flattens a JSON-LD payload (single object, list, or @graph) into nodes."""
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return graph
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def extract_handle(url: Optional[str]) -> Optional[str]:
    """Best-effort handle from a profile URL (linkedin.com/company/foo -> foo)."""
    if not url:
        return None
    try:
        path = urlparse(url).path.strip("/")
    except Exception:
        return None
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    handle = parts[-1]
    return handle or None


def _parse_count(text: Optional[str]) -> Optional[int]:
    """'1.2K followers' -> 1200, '12,340' -> 12340."""
    if not text:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*([KkMm]?)", text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    multiplier = match.group(2).lower()
    if multiplier == "k":
        value *= 1_000
    elif multiplier == "m":
        value *= 1_000_000
    return int(value)


async def fetch_social_stats(url: str, platform: str, timeout: float = 10.0) -> Dict[str, Any]:
    """
    Best-effort public profile stats from the profile page itself.

    Never raises: any failure returns {} so social enrichment can never block
    or penalise a lead.
    """
    out: Dict[str, Any] = {}
    html = await fetch_html(url, timeout=timeout)
    if not html:
        return out

    lowered = html.lower()

    for pattern, field in (
        (r"([\d.,]+\s*[KkMm]?)\s*followers", "followers"),
        (r"([\d.,]+)\s*followers", "followers"),
        (r"([\d.,]+\s*[KkMm]?)\s*following", "following"),
        (r'"follower_count"\s*:\s*(\d+)', "followers"),
        (r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)', "followers"),
    ):
        match = re.search(pattern, lowered)
        if match:
            count = _parse_count(match.group(1))
            if count is not None:
                out.setdefault(field, count)
                break

    for pattern, field in ((r'"media_count"\s*:\s*(\d+)', "posts_count"), (r"([\d.,]+)\s*posts", "posts_count")):
        match = re.search(pattern, lowered)
        if match:
            count = _parse_count(match.group(1))
            if count is not None:
                out.setdefault(field, count)
                break

    if "verified" in lowered and ("badge" in lowered or "verified account" in lowered):
        out["verified"] = True

    return out


async def find_business_socials(
    business: Any,
    homepage_html: Optional[str] = None,
    contact_socials: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Stage A: merge socials already attached to contacts, socials from the
    business homepage (fetched when not supplied), into one per-platform map.
    """
    merged: Dict[str, str] = {}

    if contact_socials and isinstance(contact_socials, dict):
        for platform, url in contact_socials.items():
            if isinstance(platform, str) and isinstance(url, str) and url:
                merged[platform] = url

    website = getattr(business, "website", None)
    html = homepage_html
    if html is None and website:
        html = await fetch_html(website)

    merged.update(extract_socials_from_html(html))
    return merged


async def probe_direct_socials(business: Any, timeout: float = 10.0) -> Dict[str, str]:
    """
    Stage B (opt-in): search the platforms directly for the business name.

    These endpoints actively block scrapers and frequently break; failures return
    {} and never affect the lead. Only enabled when LEADFORGE_SOCIAL_DIRECT=true.
    """
    name = (getattr(business, "name", None) or "").strip()
    if not name:
        return {}

    candidates: Dict[str, str] = {}
    encoded = re.sub(r"\s+", "+", name)

    searches = {
        "facebook": f"https://www.facebook.com/search/pages/?q={encoded}",
        "instagram": f"https://www.instagram.com/explore/search/keyword/?q={encoded}",
        "linkedin": f"https://www.linkedin.com/search/results/companies/?keywords={encoded}",
    }

    for platform, url in searches.items():
        html = await fetch_html(url, timeout=timeout)
        if not html:
            continue
        try:
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a", href=True):
                href = _clean_url(link["href"])
                if not href:
                    continue
                lowered = href.lower()
                if any(host in lowered for host in PLATFORM_HOSTS[platform]):
                    candidates.setdefault(platform, href)
                    break
        except Exception as e:
            logger.debug(f"[social:direct] {platform} search failed: {e}")
            continue

    return candidates


async def upsert_social_profiles(
    db,
    business_id: int,
    socials: Dict[str, str],
    provenance: str = "website",
) -> List[Any]:
    """Persists discovered social profiles, refreshing stats for new entries."""
    from app.models.social_profile import SocialProfile

    saved = []
    for platform, url in socials.items():
        if not url:
            continue
        existing = await db.execute(
            select(SocialProfile).where(
                SocialProfile.business_id == business_id,
                SocialProfile.platform == platform,
            )
        )
        profile = existing.scalars().first()

        stats: Dict[str, Any] = {}
        try:
            stats = await fetch_social_stats(url, platform)
        except Exception as e:
            logger.debug(f"[social] stats fetch failed for {platform}: {e}")

        if profile is None:
            profile = SocialProfile(
                business_id=business_id,
                platform=platform,
                url=url,
                handle=extract_handle(url),
                followers=stats.get("followers"),
                posts_count=stats.get("posts_count"),
                verified=bool(stats.get("verified")),
                source=provenance,
            )
            db.add(profile)
        else:
            profile.url = url
            profile.handle = extract_handle(url) or profile.handle
            if stats.get("followers") is not None:
                profile.followers = stats["followers"]
            if stats.get("posts_count") is not None:
                profile.posts_count = stats["posts_count"]
            if stats.get("verified"):
                profile.verified = True

        saved.append(profile)

    await db.commit()
    return saved
