"""Junk addresses, and cells that hold more than one address.

Two separate ways a contact row ends up with an email that is not an
address:

* The extraction regex matched the *package version* in a script URL -
  "bootstrap@4.0.0", "lodash@4.18.1" - and those became contact rows
  attached to real businesses.
* An Excel export puts several addresses in one cell ("a@acme.in,
  b@acme.in"), and the cell was stored verbatim, so the contact's email
  was a string that was not an address and the real addresses behind it
  were lost.
"""

import pytest
from sqlalchemy import select

from app.database import async_session_maker
from app.models.contact import Contact
from app.models.business import Business


@pytest.mark.parametrize("junk", [
    "bootstrap@4.0.0",
    "lodash@4.18.1",
    "core-js-bundle@3.2.1",
    "intl-segmenter@11.7.10",
    "aos@2.3.4",
    "react@18.3.1",
    "wght@300..900",
])
def test_a_package_version_is_not_an_address(junk):
    from app.enricher.email_finder import EMAIL_REGEX

    assert EMAIL_REGEX.search(junk) is None, f"{junk} was read as an address"


@pytest.mark.parametrize("real", [
    "info@example.in",
    "sales@acme.co.in",
    "a@b.io",
    "owner+tag@my-shop.com",
    "first.last@sub.domain.org",
    "x@y.travel",
])
def test_a_real_address_is_still_an_address(real):
    from app.enricher.email_finder import EMAIL_REGEX

    assert EMAIL_REGEX.search(real) is not None


def test_the_verifier_rejects_a_package_version():
    import re

    from app.verifier.smtp_verifier import EMAIL_REGEX

    pattern = re.compile(EMAIL_REGEX)
    assert pattern.match("bootstrap@4.0.0") is None
    assert pattern.match("info@example.in") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("email_cell", [
    '"first@acme.in, second@acme.in"',
    'first@acme.in;second@acme.in',
    'First <first@acme.in> Second <second@acme.in>',
])
async def test_a_csv_cell_with_two_addresses_creates_two_contacts(email_cell):
    """An Excel export of a "primary contact" column routinely comes out
    with several addresses in one cell."""
    csv_text = (
        "business_name,email,phone,website,address,category\n"
        f"Acme Realty,{email_cell},+919812345678,"
        "https://acme.in,Pune HQ,Real estate\n"
    )

    from httpx import AsyncClient
    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/leads/import/csv",
            json={"csv_content": csv_text},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["imported"] == 1

        # Re-importing the same row finds the business and the existing
        # addresses instead of creating duplicate businesses or contacts.
        res = await ac.post(
            "/api/v1/leads/import/csv",
            json={"csv_content": csv_text},
        )
        assert res.status_code == 200, res.text
        assert res.json()["updated"] == 1

    async with async_session_maker() as db:
        contacts = (await db.execute(select(Contact))).scalars().all()
        emails = sorted(c.email for c in contacts if c.email)
        businesses = (await db.execute(select(Business))).scalars().all()
        assert "first@acme.in" in emails
        assert "second@acme.in" in emails
        assert len(businesses) == 1
        assert len(contacts) == 2
        assert {c.business_id for c in contacts} == {businesses[0].id}
        # And nothing stored a joined string.
        assert not any("," in e or ";" in e for e in emails)
