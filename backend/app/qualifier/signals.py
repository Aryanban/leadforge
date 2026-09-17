import re
from typing import Any, Dict, List, Optional

import httpx

SOCIAL_PLATFORMS = ("linkedin", "facebook", "instagram", "twitter", "youtube")


def _contact_emails(contacts: List[Any]) -> List[str]:
    out = []
    for c in contacts or []:
        email = getattr(c, "email", None) or (c.get("email") if isinstance(c, dict) else None)
        if email:
            out.append(str(email).lower().strip())
    return out


def _contact_socials(contacts: List[Any]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for c in contacts or []:
        links = getattr(c, "social_links", None)
        if isinstance(links, dict):
            merged.update({k: v for k, v in links.items() if isinstance(v, str)})
    return merged


def extract_signals(business: Any, contacts: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    Extracts objective, network-free facts about a lead from the persisted record.

    Everything here is read off the model so that scoring stays pure and testable;
    network-dependent facts (SSL, site freshness, ad spend) are probed during
    enrichment and cached on business.extra_data.
    """
    contacts = contacts or []
    extra = getattr(business, "extra_data", None)
    if not isinstance(extra, dict):
        extra = {}

    emails = _contact_emails(contacts)
    socials = _contact_socials(contacts)
    website = getattr(business, "website", None)

    rating = getattr(business, "rating", None)
    reviews = getattr(business, "reviews_count", None)

    try:
        rating_val = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_val = None

    try:
        reviews_val = int(reviews) if reviews is not None else None
    except (TypeError, ValueError):
        reviews_val = None

    return {
        "verified_email": any(getattr(c, "is_verified", False) for c in contacts),
        "any_email": bool(emails),
        "email_count": len(emails),
        "phone": bool(getattr(business, "phone", None)),
        "whatsapp": any(getattr(c, "whatsapp_link", None) for c in contacts),
        "website": bool(website),
        "rating": rating_val,
        "reviews_count": reviews_val,
        "unclaimed_gbp": bool(extra.get("is_claimed", True) is False),
        "category": (getattr(business, "industry", None) or "").lower(),
        "name": (getattr(business, "name", None) or "").lower(),
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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False, headers=headers) as client:
            response = await client.get(url)
            out["ssl_valid"] = str(response.url).startswith("https://") and response.url.is_secure
            out["final_status_code"] = response.status_code

            if "text/html" in response.headers.get("content-type", ""):
                text = response.text
                flat = []
                for m in re.finditer(r"(19\d{2}|20\d{2})", text):
                    try:
                        flat.append(int(m.group(1)))
                    except ValueError:
                        pass
                if flat:
                    out["site_copyright_year"] = max(flat)
                    out["site_stale"] = max(flat) < 2022
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
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False, headers=headers) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return {"running_ads": None, "ad_count": None}
            text = response.text
            counts = re.findall(r"\"ad_count\"\s*:\s*(\d+)", text)
            if counts:
                n = int(counts[0])
                return {"running_ads": n > 0, "ad_count": n}
            # Some page variants embed a different key
            counts = re.findall(r"active_ads\D{0,40}(\d+)", text)
            if counts:
                n = int(counts[0])
                return {"running_ads": n > 0, "ad_count": n}
            return {"running_ads": None, "ad_count": None}
    except Exception:
        return {"running_ads": None, "ad_count": None}


async def probe_business_health(business: Any, country: str = "IN") -> Dict[str, Any]:
    """
    Runs the network-dependent probes for a lead and returns a patch to merge into
    business.extra_data so scoring stays offline and repeatable.
    """
    patch: Dict[str, Any] = {}
    website = getattr(business, "website", None)
    if website:
        patch.update(await _probe_website_health(website))
    ads = await _probe_facebook_ads(getattr(business, "name", "") or "", country=country)
    patch.update(ads)
    return patch
