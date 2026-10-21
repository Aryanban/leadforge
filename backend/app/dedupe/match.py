import re
from typing import Dict, List, Optional
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


async def build_lead_indexes(db: AsyncSession, leads: List[dict]) -> Dict[str, Dict[str, Business]]:
    """Builds the four dedupe lookup tables for a batch of leads.

    The scrape path used to run one SELECT per lead, and matched on the
    business NAME only - ignoring the place id, the phone and the domain.
    That both cost a query per lead and got the identity wrong: the same
    business whose name changed became a duplicate, and two different
    businesses that happen to share a generic Indian name ("Sharma Dental
    Clinic") were merged.

    Four grouped queries - one per key type - replace the per-lead query,
    and the lookup then happens in Python. The cost scales with the number
    of leads, not with the size of the database.
    """
    place_ids = {l.get("place_id") for l in leads if l.get("place_id")}
    phones = {normalize_phone(l.get("phone")) for l in leads if l.get("phone")}
    domains = {canonical_domain(l.get("website")) for l in leads if l.get("website")}
    names = {l.get("name") for l in leads if l.get("name")}

    by_place: Dict[str, Business] = {}
    by_phone: Dict[str, Business] = {}
    by_domain: Dict[str, Business] = {}
    by_name: Dict[str, Business] = {}

    if place_ids:
        rows = (await db.execute(
            select(Business).where(Business.place_id.in_(place_ids))
        )).scalars().all()
        for b in rows:
            if b.place_id:
                by_place.setdefault(b.place_id, b)

    if phones:
        rows = (await db.execute(
            select(Business).where(Business.phone_e164.in_(phones))
        )).scalars().all()
        for b in rows:
            if b.phone_e164:
                by_phone.setdefault(b.phone_e164, b)

    if domains:
        rows = (await db.execute(
            select(Business).where(Business.domain.in_(domains))
        )).scalars().all()
        for b in rows:
            if b.domain:
                by_domain.setdefault(b.domain, b)

    if names:
        rows = (await db.execute(
            select(Business).where(Business.name.in_(names))
        )).scalars().all()
        for b in rows:
            if b.name:
                by_name.setdefault(b.name, b)

    return {
        "place_id": by_place,
        "phone": by_phone,
        "domain": by_domain,
        "name": by_name,
    }


def match_lead(lead: dict, indexes: Dict[str, Dict[str, Business]]) -> Optional[Business]:
    """Matches a lead against prebuilt indexes, in the same priority order as
    :func:`find_existing_business`."""
    place_id = lead.get("place_id")
    if place_id:
        match = indexes["place_id"].get(place_id)
        if match is not None:
            return match

    phone = normalize_phone(lead.get("phone"))
    if phone:
        match = indexes["phone"].get(phone)
        if match is not None:
            return match

    domain = canonical_domain(lead.get("website"))
    if domain:
        match = indexes["domain"].get(domain)
        if match is not None:
            return match

    name = lead.get("name")
    if name:
        return indexes["name"].get(name)
    return None


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
