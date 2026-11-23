import httpx
import pytest
from web_search.providers.webz import DEFAULT_ENDPOINT_URL, search_webz

BLOGS_URL = "https://api.webz.io/api/blogs"

_RealAsyncClient = httpx.AsyncClient


def _mock_transport(expected_url: str, payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(expected_url)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_omitted_endpoint_url_calls_default(monkeypatch):
    transport = _mock_transport(DEFAULT_ENDPOINT_URL, {"posts": []})

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.webz.httpx.AsyncClient", fake_client)

    results = await search_webz("key", "query", 5)
    assert results == []


@pytest.mark.asyncio
async def test_endpoint_url_override_calls_that_url(monkeypatch):
    payload = {
        "posts": [
            {"url": "https://example.com/post", "title": "A Blog Post", "text": "snippet text"}
        ]
    }
    transport = _mock_transport(BLOGS_URL, payload)

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.webz.httpx.AsyncClient", fake_client)

    results = await search_webz("key", "query", 5, endpoint_url=BLOGS_URL)

    assert len(results) == 1
    assert results[0].link == "https://example.com/post"
    assert results[0].title == "A Blog Post"
    assert results[0].snippet == "snippet text"


@pytest.mark.asyncio
async def test_blank_endpoint_url_raises():
    with pytest.raises(ValueError, match="webz"):
        await search_webz("key", "query", 5, endpoint_url="")


@pytest.mark.asyncio
async def test_malformed_endpoint_url_raises():
    with pytest.raises(ValueError, match="webz"):
        await search_webz("key", "query", 5, endpoint_url="/api/blogs")
