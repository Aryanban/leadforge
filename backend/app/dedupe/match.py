import re
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business
from app.models.contact import Contact

LEGAL_TOKENS = {
    "ltd", "limited", "llp", "pvt", "private", "inc", "incorporated",
    "corp", "corporation", "co", "company", "the", "and", "enterprises",
    "solutions", "services", "associates", "group", "traders", "agency",
}


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """Reduces a phone string to comparable digits (Indian formats handled)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits or None


def canonical_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        host = urlparse(url if "://" in url else f"http://{url}").netloc.lower()
    except Exception:
        return None
    host = host.split(":")[0]
    host = re.sub(r"^www\.", "", host).strip()
    return host or None


def normalize_name(name: Optional[str]) -> str:
    """Legal-suffix-stripped lowercase name for exact-match dedupe."""
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    tokens = [t for t in cleaned.split() if t and t not in LEGAL_TOKENS]
    return " ".join(tokens)


async def find_existing_business(db: AsyncSession, lead: dict) -> Optional[Business]:
    """Match a raw lead to an existing business by place_id, phone, domain, or name.

    The phone branch used to compare a *normalised* value against the raw
    stored string ("9822522560" vs "+91 98225 22560"), so it could never
    match - the phone dedupe was dead code. It now matches on the derived
    ``phone_e164`` column as well as the raw forms.

    The domain branch used to be a substring match, so ``example.com``
    matched ``smileshop.example.com`` - a silent false merge. It is now an
    exact host comparison.
    """
    place_id = lead.get("place_id")
    if place_id:
        res = await db.execute(select(Business).where(Business.place_id == place_id))
        match = res.scalars().first()
        if match:
            return match

    raw_phone = lead.get("phone")
    phone = normalize_phone(raw_phone)
    if phone:
        res = await db.execute(
            select(Business).where(
                or_(
                    Business.phone_e164 == phone,
                    Business.phone == raw_phone,
                    Business.phone == phone,
                )
            )
        )
        match = res.scalars().first()
        if match:
            return match

        res = await db.execute(
            select(Contact).where(
                or_(Contact.phone == raw_phone, Contact.phone == phone)
            )
        )
        contact = res.scalars().first()
        if contact and contact.business_id:
            return await db.get(Business, contact.business_id)

    domain = canonical_domain(lead.get("website"))
    if domain:
        res = await db.execute(
            select(Business).where(
                or_(
                    Business.domain == domain,
                    Business.website == lead.get("website"),
                )
            )
        )
        match = res.scalars().first()
        if match:
            return match

    # Name matching stays exact and raw on purpose. Indian SMBs have very
    # generic names ("Sharma Dental Clinic", "Krishna Medicals"), so a
    # looser match - or a normalised one that strips legal suffixes - would
    # merge genuinely different businesses in different cities.
    name = lead.get("name")
    if name:
        res = await db.execute(select(Business).where(Business.name == name))
        match = res.scalars().first()
        if match:
            return match

    return None
