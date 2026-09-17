import pytest
from sqlalchemy import select

from app.enricher.social_finder import (
    _parse_count,
    extract_handle,
    extract_socials_from_html,
)
from app.models.business import Business
from app.models.social_profile import SocialProfile

SAMPLE_HTML = """
<html>
<body>
  <a href="https://facebook.com/MyClinic">Facebook</a>
  <a href="https://www.instagram.com/myclinic_delhi">Instagram</a>
  <a href="https://twitter.com/share?text=hi">Share (ignored)</a>
  <a href="/contact">Internal</a>
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"Dentist",
   "name":"My Clinic","sameAs":["https://www.linkedin.com/company/my-clinic","https://youtube.com/@myclinic"]}
  </script>
</body>
</html>
"""


def test_extract_socials_from_href_and_jsonld():
    socials = extract_socials_from_html(SAMPLE_HTML)
    assert socials["facebook"] == "https://facebook.com/MyClinic"
    assert socials["instagram"] == "https://www.instagram.com/myclinic_delhi"
    assert socials["linkedin"] == "https://www.linkedin.com/company/my-clinic"
    assert socials["youtube"].startswith("https://youtube.com/")
    # Share links must be filtered out
    assert "twitter" not in socials


def test_extract_socials_empty_and_broken_inputs():
    assert extract_socials_from_html(None) == {}
    assert extract_socials_from_html("") == {}
    assert extract_socials_from_html("<p>no links here</p>") == {}

    broken_ld = '<script type="application/ld+json">{not json}</script>'
    assert extract_socials_from_html(broken_ld) == {}


def test_extract_handle_from_urls():
    assert extract_handle("https://www.instagram.com/myclinic_delhi") == "myclinic_delhi"
    assert extract_handle("https://linkedin.com/company/my-clinic") == "my-clinic"
    assert extract_handle("https://youtube.com/@myclinic") == "@myclinic"
    assert extract_handle(None) is None


def test_count_parsing():
    assert _parse_count("1.2K followers") == 1200
    assert _parse_count("3M followers") == 3000000
    assert _parse_count("12,340 followers") == 12340
    assert _parse_count("no numbers here") is None


@pytest.mark.asyncio
async def test_social_profiles_persist_and_update(db_session, monkeypatch):
    business = Business(name="My Clinic", industry="Dentist", source="test")
    db_session.add(business)
    await db_session.commit()
    await db_session.refresh(business)

    async def fake_stats(url, platform, timeout=10.0):
        return {"followers": 1500, "posts_count": 42}

    monkeypatch.setattr("app.enricher.social_finder.fetch_social_stats", fake_stats)

    from app.enricher.social_finder import upsert_social_profiles

    saved = await upsert_social_profiles(
        db_session, business.id, {"instagram": "https://www.instagram.com/myclinic_delhi"}
    )
    assert len(saved) == 1
    assert saved[0].platform == "instagram"
    assert saved[0].followers == 1500

    res = await db_session.execute(select(SocialProfile).where(SocialProfile.business_id == business.id))
    assert len(res.scalars().all()) == 1

    # Re-running with a second platform keeps the first and adds the new one
    await upsert_social_profiles(
        db_session,
        business.id,
        {
            "instagram": "https://www.instagram.com/myclinic_delhi",
            "facebook": "https://facebook.com/MyClinic",
        },
    )
    res = await db_session.execute(select(SocialProfile).where(SocialProfile.business_id == business.id))
    platforms = {p.platform for p in res.scalars().all()}
    assert platforms == {"instagram", "facebook"}
