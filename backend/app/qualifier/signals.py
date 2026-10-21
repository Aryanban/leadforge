import asyncio
import re
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import inspect as sa_inspect

SOCIAL_PLATFORMS = ("linkedin", "facebook", "instagram", "twitter", "youtube")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _contact_emails(contacts: List[Any]) -> List[str]:
    out = []
    for c in contacts or []:
        email = _get(c, "email")
        if email:
            out.append(str(email).lower().strip())
    return out


def _contact_socials(contacts: List[Any]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for c in contacts or []:
        links = _get(c, "social_links")
        if isinstance(links, dict):
            merged.update({k: v for k, v in links.items() if isinstance(v, str)})
    return merged


def _business_socials(business: Any) -> Dict[str, str]:
    """Reads persisted SocialProfile rows, only when the relation is already loaded."""
    if isinstance(business, dict):
        return business.get("social_profiles") or {}
    try:
        state = sa_inspect(business)
        if "social_profiles" in state.unloaded:
            return {}
        profiles = getattr(business, "social_profiles", None) or []
        return {p.platform: p.url for p in profiles if getattr(p, "platform", None)}
    except Exception:
        return {}


def extract_signals(business: Any, contacts: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Extracts objective, network-free facts about a lead from the persisted record.

    Everything here is read off the model so that scoring stays pure and testable;
    network-dependent facts (SSL, site freshness, ad spend) are probed during
    enrichment and cached on business.extra_data.
    """
    contacts = contacts or []
    extra = _get(business, "extra_data")
    if not isinstance(extra, dict):
        extra = {}

    emails = _contact_emails(contacts)
    socials = {**_business_socials(business), **_contact_socials(contacts)}
    website = _get(business, "website")

    rating = _get(business, "rating")
    reviews = _get(business, "reviews_count")

    try:
        rating_val = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_val = None

    try:
        reviews_val = int(reviews) if reviews is not None else None
    except (TypeError, ValueError):
        reviews_val = None

    # Mobile vs landline is *independent* information: a landline-only lead
    # cannot be reached on WhatsApp, which is the primary channel for Indian
    # SMBs. The previous "whatsapp" signal was derived mechanically from the
    # same phone number, so it could never disagree with "phone" - 15 of the
    # 100 score points were free.
    phone_raw = _get(business, "phone")
    mobile_line = False
    line_type = extra.get("line_type")
    if line_type:
        mobile_line = str(line_type).lower() in ("mobile", "cell", "mobile_line")
    elif phone_raw:
        try:
            from app.sources.in_phone import is_mobile
            mobile_line = bool(is_mobile(phone_raw))
        except Exception:
            mobile_line = False

    return {
        "verified_email": any(bool(_get(c, "is_verified", False)) for c in contacts),
        "any_email": bool(emails),
        "email_count": len(emails),
        "phone": bool(phone_raw),
        "whatsapp": any(bool(_get(c, "whatsapp_link")) for c in contacts),
        "mobile_line": mobile_line,
        "website": bool(website),
        "rating": rating_val,
        "reviews_count": reviews_val,
        "unclaimed_gbp": bool(extra.get("is_claimed", True) is False),
        "category": (_get(business, "industry") or "").lower(),
        "name": (_get(business, "name") or "").lower(),
        "social_presence": bool(socials),
        "social_platforms": sorted(socials.keys()),
        "ssl_valid": extra.get("ssl_valid"),
        "site_stale": extra.get("site_stale"),
        "running_ads": extra.get("running_ads"),
        "ad_count": extra.get("ad_count"),
    }


async def _probe_website_health(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Quick HEAD/GET to determine TLS validity and site freshness signals."""
    if not url:
        return {}
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    out: Dict[str, Any] = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url)
            out["ssl_valid"] = str(response.url).startswith("https://") and response.url.is_secure
            out["final_status_code"] = response.status_code

            if "text/html" in response.headers.get("content-type", ""):
                text = response.text
                # Look for a *year* the site claims, not any 4-digit number.
                # The old regex matched every 4-digit number in the page, so a
                # price of "2024" or a stray number in a CSS comment made a
                # brand-new site look stale - which flipped the
                # "agency_opportunity" preset's signal to the wrong side.
                years: List[int] = []
                for pattern in (
                    r"(?:©|&copy;|copyright)\s*(?:\(c\))?\s*(\d{4})",
                    r"copyright[^0-9]{0,24}(\d{4})",
                    r"(?:©|&copy;)\s*(\d{4})\s*[-–—]",
                    r"\b(?:last\s+updated|established|since|founded)\b[^0-9]{0,24}(\d{4})",
                ):
                    for m in re.finditer(pattern, text, re.IGNORECASE):
                        try:
                            years.append(int(m.group(1)))
                        except (ValueError, IndexError):
                            pass
                if years:
                    out["site_copyright_year"] = max(years)
                    out["site_stale"] = max(years) < 2022
                last_mod = response.headers.get("last-modified")
                if last_mod:
                    out["last_modified"] = last_mod
    except Exception:
        out["ssl_valid"] = None
    return out


async def _probe_facebook_ads(business_name: str, country: str = "IN", timeout: float = 12.0) -> Dict[str, Any]:
    """
    Checks the public Facebook Ad Library (no login required) for currently active ads.

    Returns {running_ads: bool|None, ad_count: int|None}. Failures degrade to None
    (unknown) and never block or penalise a lead.
    """
    if not business_name:
        return {}
    query = re.sub(r"[^\w\s]", " ", business_name).strip()
    url = (
        "https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country={country}&q={httpx.URL(query)}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            # The Ad Library page is multi-megabyte of markup and all we
            # want is two numbers in it. Streaming and stopping at the first
            # match turns a multi-MB download into a few KB - this runs once
            # per enriched lead, so the saving is multiplied by the whole
            # corpus.
            buffer = ""
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    return {"running_ads": None, "ad_count": None}
                async for chunk in response.aiter_text():
                    buffer += chunk
                    match = re.search(r"\"ad_count\"\s*:\s*(\d+)", buffer)
                    if match:
                        n = int(match.group(1))
                        return {"running_ads": n > 0, "ad_count": n}
                    # Some page variants embed a different key
                    match = re.search(r"active_ads\D{0,40}(\d+)", buffer)
                    if match:
                        n = int(match.group(1))
                        return {"running_ads": n > 0, "ad_count": n}
                    if len(buffer) > 2_000_000:
                        break
            return {"running_ads": None, "ad_count": None}
    except Exception:
        return {"running_ads": None, "ad_count": None}


async def probe_business_health(business: Any, country: str = "IN") -> Dict[str, Any]:
    """
    Runs the network-dependent probes for a lead and returns a patch to merge into
    business.extra_data so scoring stays offline and repeatable.

    The website probe and the Facebook Ad Library probe are independent
    network calls, so they run concurrently. Sequentially they cost the sum
    of both timeouts (up to ~22 seconds per lead); concurrently it is the
    slower of the two.
    """
    website = getattr(business, "website", None)
    name = getattr(business, "name", "") or ""

    site_probe, ads_probe = await asyncio.gather(
        _probe_website_health(website) if website else _empty_probe(),
        _probe_facebook_ads(name, country=country),
        return_exceptions=True,
    )

    patch: Dict[str, Any] = {}
    if isinstance(site_probe, dict):
        patch.update(site_probe)
    if isinstance(ads_probe, dict):
        patch.update(ads_probe)
    return patch


async def _empty_probe() -> Dict[str, Any]:
    """A no-op probe result, so both branches can be awaited uniformly."""
    return {}
