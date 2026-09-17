from types import SimpleNamespace

import pytest

from app.sources.base import Source, raw_lead
from app.sources.router import BY_NAME, discover, list_available_sources, select_sources
from app.sources.justdial import JustDialSource
from app.sources.http_utils import extract_city


class FakeSource(Source):
    name = "fake"

    def supports(self, niche, area):
        return True

    async def search(self, niche, area, limit=20):
        return [raw_lead(name=f"{niche} Lead {i}", source=self.name, query=self.build_query(niche, area)) for i in range(limit)]


@pytest.fixture
def fake_registry(monkeypatch):
    fake = FakeSource()
    monkeypatch.setattr("app.sources.router.REGISTRY", [fake])
    monkeypatch.setattr("app.sources.router.BY_NAME", {"fake": fake})
    return fake


def test_source_interface_requires_implementation():
    class Incomplete(Source):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_build_query_joins_niche_and_area():
    source = JustDialSource()
    assert source.build_query("Dentists", "South Delhi") == "Dentists in South Delhi"
    assert source.build_query("Dentists", None) == "Dentists"


def test_extract_city_maps_areas_to_cities():
    assert extract_city("Rohini Delhi") == "delhi"
    assert extract_city("South Delhi") == "delhi"
    assert extract_city("Delhi NCR") == "delhi"
    assert extract_city("Koramangala Bengaluru") == "bangalore"
    assert extract_city(None) is None


def test_justdial_supports_only_with_area():
    source = JustDialSource()
    assert source.supports("Dentists", "Delhi") is True
    assert source.supports("Dentists", None) is False


def test_available_sources_lists_registry():
    sources = list_available_sources()
    names = {s["name"] for s in sources}
    assert "google_maps" in names
    assert {"justdial", "indiamart", "sulekha"} <= names


@pytest.mark.asyncio
async def test_select_sources_prefers_manual_override(monkeypatch):
    fake = FakeSource()
    justdial = JustDialSource()
    monkeypatch.setattr("app.sources.router.REGISTRY", [fake, justdial])
    monkeypatch.setattr("app.sources.router.BY_NAME", {"fake": fake, "justdial": justdial})

    profile = SimpleNamespace(preferred_sources=["justdial"])
    chosen = await select_sources("Dentists", "Delhi", profile)

    assert chosen[0].name == "justdial"


@pytest.mark.asyncio
async def test_discover_groups_by_source(fake_registry):
    results = await discover("Dentists", "Delhi", limit=5)
    assert "fake" in results
    assert len(results["fake"]) == 5
    assert results["fake"][0]["source"] == "fake"


@pytest.mark.asyncio
async def test_discover_respects_source_override(fake_registry, monkeypatch):
    results = await discover("Dentists", "Delhi", limit=3, sources=["fake"])
    assert list(results.keys()) == ["fake"]


@pytest.mark.asyncio
async def test_discover_isolates_source_failures(monkeypatch):
    class Boom(Source):
        name = "boom"

        def supports(self, niche, area):
            return True

        async def search(self, niche, area, limit=20):
            raise RuntimeError("upstream is down")

    import app.sources.router as router

    monkeypatch.setattr(router, "REGISTRY", [Boom()])
    monkeypatch.setattr(router, "BY_NAME", {"boom": Boom()})

    results = await discover("Dentists", "Delhi", limit=5)
    assert results == {"boom": []}
