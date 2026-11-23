import httpx
import pytest
from web_search.providers.perplexity import search_perplexity

_RealAsyncClient = httpx.AsyncClient

CUSTOM_URL = "https://custom.example.com/search"


def _mock_transport(expected_url: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == expected_url
        return httpx.Response(200, json={"results": []})

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, expected_url: str):
    transport = _mock_transport(expected_url)

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.perplexity.httpx.AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_default_unchanged(monkeypatch):
    _patch_client(monkeypatch, "https://api.perplexity.ai/search")
    results = await search_perplexity("key", "query", 5)
    assert results == []


@pytest.mark.asyncio
async def test_legacy_api_url_still_works_and_warns(monkeypatch, caplog):
    _patch_client(monkeypatch, CUSTOM_URL)
    with caplog.at_level("WARNING"):
        results = await search_perplexity("key", "query", 5, api_url=CUSTOM_URL)
    assert results == []
    assert any("deprecated" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_endpoint_url_wins_over_api_url(monkeypatch):
    other_url = "https://other.example.com/search"
    _patch_client(monkeypatch, other_url)
    results = await search_perplexity(
        "key", "query", 5, api_url=CUSTOM_URL, endpoint_url=other_url
    )
    assert results == []


@pytest.mark.asyncio
async def test_blank_endpoint_url_raises_even_with_valid_api_url():
    with pytest.raises(ValueError, match="perplexity"):
        await search_perplexity("key", "query", 5, api_url=CUSTOM_URL, endpoint_url="")


@pytest.mark.asyncio
async def test_explicit_null_api_url_raises_without_falling_back_to_default():
    with pytest.raises(ValueError, match="perplexity"):
        await search_perplexity("key", "query", 5, api_url=None)
