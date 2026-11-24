import httpx
import pytest
from web_search.providers.searxng import search_searxng

_RealAsyncClient = httpx.AsyncClient

QUERY_URL = "https://searxng.example.com/search"
ENDPOINT_URL = "https://other-searxng.example.com/search"


def _mock_transport(expected_url: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(expected_url)
        return httpx.Response(200, json={"results": []})

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, expected_url: str):
    transport = _mock_transport(expected_url)

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.searxng.httpx.AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_query_url_only_path_unchanged(monkeypatch):
    _patch_client(monkeypatch, QUERY_URL)
    results = await search_searxng(QUERY_URL, "query", 5)
    assert results == []


@pytest.mark.asyncio
async def test_query_url_placeholder_stripped(monkeypatch):
    placeholder_url = "https://searxng.example.com/search?q=<query>"
    captured_urls = []
    transport = _mock_transport(QUERY_URL)
    original_get = _RealAsyncClient.get

    async def capturing_get(self, url, *args, **kwargs):
        captured_urls.append(str(url))
        return await original_get(self, url, *args, **kwargs)

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.searxng.httpx.AsyncClient", fake_client)
    monkeypatch.setattr(_RealAsyncClient, "get", capturing_get)

    results = await search_searxng(placeholder_url, "query", 5)

    assert results == []
    assert captured_urls == [QUERY_URL]


@pytest.mark.asyncio
async def test_endpoint_url_only_succeeds(monkeypatch):
    """Regression: previously raised TypeError on missing 'query_url' before signature change."""
    _patch_client(monkeypatch, ENDPOINT_URL)
    results = await search_searxng(query="query", count=5, endpoint_url=ENDPOINT_URL)
    assert results == []


@pytest.mark.asyncio
async def test_both_omitted_raises_value_error():
    with pytest.raises(ValueError, match="searxng"):
        await search_searxng(query="query", count=5)


@pytest.mark.asyncio
async def test_endpoint_url_wins_over_query_url(monkeypatch):
    _patch_client(monkeypatch, ENDPOINT_URL)
    results = await search_searxng(
        QUERY_URL, "query", 5, endpoint_url=ENDPOINT_URL
    )
    assert results == []


@pytest.mark.asyncio
async def test_blank_endpoint_url_raises_even_with_valid_query_url():
    with pytest.raises(ValueError, match="searxng"):
        await search_searxng(QUERY_URL, "query", 5, endpoint_url="")


@pytest.mark.asyncio
async def test_missing_query_raises_type_error():
    with pytest.raises(TypeError):
        await search_searxng(QUERY_URL, count=5)


@pytest.mark.asyncio
async def test_missing_count_raises_type_error():
    with pytest.raises(TypeError):
        await search_searxng(QUERY_URL, query="query")
