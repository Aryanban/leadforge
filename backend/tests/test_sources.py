"""The directory source adapters, and the HTTP layer underneath them.

Two classes of regression live here:

* Selectors drift. Sulekha replaced ``li.biz-listing`` with a Tailwind card
  whose name lives in an ``<h3>``; the adapter kept returning zero leads
  and nobody noticed because a directory with no results looks the same as
  a source that is simply broken. The fixture test pins the current
  selectors.

* The HTTP layer silently stopped working. ``fetch_html`` passed
  ``proxy=`` to ``AsyncClient.get()``, a keyword httpx 0.26 (the pinned
  version) does not have. Every call raised ``TypeError``, the exception
  was swallowed by the retry loop, and every directory source returned
  nothing for the same reason.
"""

import asyncio
import os

import httpx
import pytest

from app.sources import http_utils
from app.sources.http_utils import fetch_html
from app.sources.indiamart import IndiaMARTSource
from app.sources.justdial import JustDialSource
from app.sources.sulekha import SulekhaSource

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------


def test_per_request_proxy_detection_returns_a_bool():
    """The capability probe must never raise, whatever httpx is installed."""
    assert isinstance(http_utils._supports_per_request_proxy(), bool)


@pytest.mark.asyncio
async def test_fetch_html_works_on_the_pinned_httpx(monkeypatch):
    """A plain fetch must return the body, not None.

    This is the regression that made every directory source look empty:
    ``proxy=`` was passed to ``AsyncClient.get()``, which httpx 0.26 does
    not accept, and the TypeError was swallowed by the retry loop.
    """
    def handler(request):
        return httpx.Response(200, text="<html><body>a listing page</body></html>")

    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    # Force the "old httpx" branch, which is what the pin actually gives us.
    monkeypatch.setattr(http_utils, "_supports_per_request_proxy", lambda: False)

    body = await fetch_html("https://example.test/listing", retries=0)
    assert body == "<html><body>a listing page</body></html>"


@pytest.mark.asyncio
async def test_fetch_html_never_passes_proxy_to_get_on_old_httpx(monkeypatch):
    """On httpx 0.26 the proxy belongs on the client, not on the request."""
    calls = []

    class _OldStyleClient:
        """Mirrors httpx 0.26: ``get()`` has no ``proxy`` keyword."""

        def __init__(self, **kwargs):
            self.init_kwargs = kwargs
            self.request_kwargs = None

        async def get(self, url, headers=None, **kwargs):
            # httpx 0.26 would raise TypeError on an unexpected keyword.
            unexpected = set(kwargs) - {"timeout", "follow_redirects", "extensions"}
            assert not unexpected, f"get() got unexpected keyword(s): {unexpected}"
            self.request_kwargs = kwargs
            calls.append(self)
            return _FakeResponse("<html><body>a listing page</body></html>")

        async def aclose(self):
            pass

    class _FakeResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

    monkeypatch.setattr(httpx, "AsyncClient", _OldStyleClient)
    monkeypatch.setattr(http_utils, "_supports_per_request_proxy", lambda: False)
    monkeypatch.setattr(http_utils, "_proxy_pool", lambda: ["http://proxy.test:8080"])

    body = await fetch_html("https://example.test/listing", retries=0)

    assert body == "<html><body>a listing page</body></html>"
    assert len(calls) == 1
    # The proxy went on the client, where httpx 0.26 wants it.
    assert calls[0].init_kwargs.get("proxy") == "http://proxy.test:8080"


@pytest.mark.asyncio
async def test_fetch_html_uses_per_request_proxy_when_supported(monkeypatch):
    """On httpx >= 0.28 the proxy can be rotated per attempt."""
    seen = []

    class _NewStyleClient:
        def __init__(self, **kwargs):
            self.init_kwargs = kwargs

        async def get(self, url, headers=None, **kwargs):
            seen.append(kwargs)
            return _FakeResponse("<html><body>a listing page</body></html>")

        async def aclose(self):
            pass

    class _FakeResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

    monkeypatch.setattr(httpx, "AsyncClient", _NewStyleClient)
    monkeypatch.setattr(http_utils, "_supports_per_request_proxy", lambda: True)
    monkeypatch.setattr(http_utils, "_proxy_pool", lambda: ["http://proxy.test:8080"])

    body = await fetch_html("https://example.test/listing", retries=0)

    assert body == "<html><body>a listing page</body></html>"
    assert seen[0].get("proxy") == "http://proxy.test:8080"


@pytest.mark.asyncio
async def test_fetch_html_reuses_one_client_across_attempts(monkeypatch):
    """Connection reuse is the cheap win; a client per attempt throws it away."""
    created = []

    class _CountingClient:
        def __init__(self, **kwargs):
            created.append(self)

        async def get(self, url, headers=None, **kwargs):
            return _FakeResponse("<html><body>blocked by the edge</body></html>", status_code=403)

        async def aclose(self):
            pass

    class _FakeResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

    monkeypatch.setattr(httpx, "AsyncClient", _CountingClient)
    monkeypatch.setattr(http_utils, "_supports_per_request_proxy", lambda: False)
    monkeypatch.setattr(http_utils, "_proxy_pool", lambda: [None])
    # No backoff sleep, so the test stays fast. Note: `http_utils.asyncio`
    # is the global asyncio module, so this patch is process-wide - the
    # replacement must therefore not call asyncio.sleep itself.
    async def _no_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr(http_utils.asyncio, "sleep", _no_sleep)

    result = await fetch_html("https://example.test/listing", retries=2)

    assert result is None
    assert len(created) == 1, "a client per attempt defeats connection reuse"


# --------------------------------------------------------------------------
# Sulekha
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sulekha_parses_the_saved_listing_page(monkeypatch):
    """The current card markup yields a name, an address and a score."""
    html = _fixture("sulekha_listing.html")

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return html

    monkeypatch.setattr("app.sources.sulekha.fetch_html", _fake_fetch)

    leads = await SulekhaSource().search("dentists", "Pune", 10)

    assert leads, "the fixture should yield at least one listing"
    assert len(leads) >= 1

    first = leads[0]
    assert first["name"]
    assert first["address"], "the card markup carries the address"
    assert first["source"] == "sulekha"
    assert first["industry"] == "Dentists"


@pytest.mark.asyncio
async def test_sulekha_score_is_kept_off_the_google_rating_scale(monkeypatch):
    """Sulekha rates out of 10. Folding that into `rating` corrupts 0-5."""
    html = _fixture("sulekha_listing.html")

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return html

    monkeypatch.setattr("app.sources.sulekha.fetch_html", _fake_fetch)

    leads = await SulekhaSource().search("dentists", "Pune", 10)

    scored = [lead for lead in leads if lead.get("source_score") is not None]
    assert scored, "the fixture contains scored listings"

    for lead in scored:
        assert lead["rating"] is None, "a /10 score must not land in a /5 field"
        assert lead["source_score_max"] == 10.0
        assert 0 <= lead["source_score"] <= 10.0


@pytest.mark.asyncio
async def test_sulekha_reports_the_verified_badge(monkeypatch):
    """The 'Verified by the Sulekha team' badge is a real quality signal."""
    html = _fixture("sulekha_listing.html")

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return html

    monkeypatch.setattr("app.sources.sulekha.fetch_html", _fake_fetch)

    leads = await SulekhaSource().search("dentists", "Pune", 10)

    assert any(lead.get("source_verified") for lead in leads)


@pytest.mark.asyncio
async def test_sulekha_reports_failure_when_the_markup_changes(monkeypatch):
    """No listings must be a loud, explained failure - never a silent []."""

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return "<html><body><p>redesigned</p></body></html>"

    monkeypatch.setattr("app.sources.sulekha.fetch_html", _fake_fetch)

    source = SulekhaSource()
    leads = await source.search("dentists", "Pune", 10)

    assert leads == []
    assert source._last_note, "a failed source must record why"
    health = await source.health()
    assert health["available"] is False or health["note"]


# --------------------------------------------------------------------------
# IndiaMART
# --------------------------------------------------------------------------


def test_indiamart_rejects_a_promoted_slot_that_does_not_match_the_niche():
    """IndiaMART serves the same promoted slots for every query.

    Without a keyword guard, a search for "dentists" returns cotton-t-shirt
    manufacturers - the silent-garbage failure.
    """
    source = IndiaMARTSource()
    assert source._matches_niche("Bulk t-shirts manufacturer", "dentists") is False
    assert source._matches_niche("Verified cotton t-shirts supplier", "dentists") is False
    assert source._matches_niche("Cotton T-Shirt Manufacturers", "cotton t-shirts") is True


@pytest.mark.asyncio
async def test_indiamart_returns_nothing_for_a_service_niche(monkeypatch):
    """IndiaMART is a product directory; a service niche must yield nothing."""
    html = (
        "<html><body>"
        "<section class='staticListingWidget'><h2>Bulk t-shirts manufacturer</h2>"
        "<div class='staticSupplierBox'><strong>Delhi</strong></div></section>"
        "</body></html>"
    )

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return html

    monkeypatch.setattr("app.sources.indiamart.fetch_html", _fake_fetch)

    source = IndiaMARTSource()
    leads = await source.search("dentists", "Pune", 10)

    assert leads == []
    assert source._last_note
    assert "dentists" in source._last_note


@pytest.mark.asyncio
async def test_indiamart_uses_the_url_that_actually_serves_a_page(monkeypatch):
    """`www.indiamart.com/search.php` 404s; the .mp path is the live one."""
    seen = {}

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        seen["url"] = url
        return "<html><body></body></html>"

    monkeypatch.setattr("app.sources.indiamart.fetch_html", _fake_fetch)

    await IndiaMARTSource().search("dentists", "Pune", 10)

    assert "search.mp" in seen["url"]
    assert "ss=dentists" in seen["url"]
    assert "city=pune" in seen["url"]


# --------------------------------------------------------------------------
# JustDial
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_justdial_uses_the_host_that_serves_content(monkeypatch):
    """`www.justdial.com` answers with a 14-byte stub; wap serves the page."""
    seen = {}

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        seen["url"] = url
        return "<html><body></body></html>"

    monkeypatch.setattr("app.sources.justdial.fetch_html", _fake_fetch)

    await JustDialSource().search("dentists", "Pune", 10)

    assert "wap.justdial.com" in seen["url"]
    assert "/pune/dentists" in seen["url"]


@pytest.mark.asyncio
async def test_justdial_explains_why_it_returns_nothing(monkeypatch):
    """A client-side listing grid must be reported, not silently empty."""

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return "<html><body><div id='__NEXT_DATA__'>{}</div></body></html>"

    monkeypatch.setattr("app.sources.justdial.fetch_html", _fake_fetch)

    source = JustDialSource()
    leads = await source.search("dentists", "Pune", 10)

    assert leads == []
    assert source._last_note
    assert "client-side" in source._last_note


@pytest.mark.asyncio
async def test_justdial_health_reports_the_truth(monkeypatch):
    """health() must not claim a source is available when it returns nothing."""

    async def _fake_fetch(url, timeout=15.0, **kwargs):
        return "<html><body><div id='__NEXT_DATA__'>{}</div></body></html>"

    monkeypatch.setattr("app.sources.justdial.fetch_html", _fake_fetch)

    health = await JustDialSource().health()

    assert health["available"] is False
    assert health["note"]
