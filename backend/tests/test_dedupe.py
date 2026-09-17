import pytest

from app.dedupe.match import (
    canonical_domain,
    find_existing_business,
    normalize_name,
    normalize_phone,
)
from app.models.business import Business


def test_normalize_phone_handles_indian_formats():
    assert normalize_phone("+91 98112 34567") == "9811234567"
    assert normalize_phone("09811234567") == "9811234567"
    assert normalize_phone("919811234567") == "9811234567"
    assert normalize_phone("+1 555 123 4567") == "15551234567"
    assert normalize_phone(None) is None
    assert normalize_phone("") is None


def test_canonical_domain_strips_scheme_and_www():
    assert canonical_domain("https://www.example.in/") == "example.in"
    assert canonical_domain("http://example.in/contact") == "example.in"
    assert canonical_domain("example.in") == "example.in"
    assert canonical_domain(None) is None
    # lstrip-style bugs would corrupt domains starting with w
    assert canonical_domain("https://williamson.co") == "williamson.co"


def test_normalize_name_strips_legal_suffixes():
    assert normalize_name("Aggarwal Real Estate Pvt Ltd") == "aggarwal real estate"
    assert normalize_name("Balaji Properties & Developers") == "balaji properties developers"
    assert normalize_name(None) == ""


@pytest.mark.asyncio
async def test_find_existing_by_place_id(db_session):
    existing = Business(
        place_id="ChIJabc123", name="A One Dentist", industry="Dentist", source="google_maps"
    )
    db_session.add(existing)
    await db_session.commit()

    match = await find_existing_business(db_session, {"place_id": "ChIJabc123", "name": "A One Dentist"})
    assert match is not None
    assert match.id == existing.id

    none = await find_existing_business(db_session, {"place_id": "ChIJxyz999", "name": "B Two Dentist"})
    assert none is None


@pytest.mark.asyncio
async def test_find_existing_by_phone(db_session):
    existing = Business(name="Care Dental", phone="+91 98112 34567", industry="Dentist")
    db_session.add(existing)
    await db_session.commit()

    match = await find_existing_business(db_session, {"name": "Care Dental", "phone": "09811234567"})
    assert match is not None
    assert match.id == existing.id


@pytest.mark.asyncio
async def test_find_existing_by_domain(db_session):
    existing = Business(name="Smile Clinic", website="https://smileclinic.in")
    db_session.add(existing)
    await db_session.commit()

    match = await find_existing_business(db_session, {"name": "Smile Clinic", "website": "smileclinic.in/about"})
    assert match is not None
    assert match.id == existing.id
