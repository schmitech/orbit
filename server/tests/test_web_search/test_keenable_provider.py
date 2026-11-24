import json

import httpx
import pytest
from web_search.providers.keenable import (
    DEFAULT_ENDPOINT_URL,
    DEFAULT_PUBLIC_ENDPOINT_URL,
    search_keenable,
)
from web_search.registry import get_provider

_RealAsyncClient = httpx.AsyncClient


def _install(monkeypatch, payload: dict, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)

    def fake_client(*args, **kwargs):
        return _RealAsyncClient(transport=transport)

    monkeypatch.setattr("web_search.providers.keenable.httpx.AsyncClient", fake_client)


PAYLOAD = {
    "results": [
        {"url": "https://example.com/a", "title": "Result A", "snippet": "snippet a"},
        {"url": "https://docs.example.org/b", "title": "Result B", "snippet": "snippet b"},
        {"title": "no url, dropped"},
    ]
}


def test_registered():
    assert get_provider("keenable") is search_keenable


@pytest.mark.asyncio
async def test_keyless_uses_public_endpoint(monkeypatch):
    seen: list[httpx.Request] = []
    _install(monkeypatch, PAYLOAD, seen)

    results = await search_keenable("query", 5)

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == DEFAULT_PUBLIC_ENDPOINT_URL
    assert "x-api-key" not in request.headers
    assert request.headers["x-keenable-title"] == "orbit"
    assert json.loads(request.content) == {"query": "query", "max_results": 5}
    assert [r.link for r in results] == ["https://example.com/a", "https://docs.example.org/b"]
    assert results[0].title == "Result A"
    assert results[0].snippet == "snippet a"


@pytest.mark.asyncio
async def test_blank_key_is_keyless(monkeypatch):
    seen: list[httpx.Request] = []
    _install(monkeypatch, {"results": []}, seen)

    assert await search_keenable("query", 5, api_key="  ") == []
    assert str(seen[0].url) == DEFAULT_PUBLIC_ENDPOINT_URL
    assert "x-api-key" not in seen[0].headers


@pytest.mark.asyncio
async def test_key_uses_keyed_endpoint(monkeypatch):
    seen: list[httpx.Request] = []
    _install(monkeypatch, {"results": []}, seen)

    await search_keenable("query", 5, api_key="secret", app_title="my-app")

    assert str(seen[0].url) == DEFAULT_ENDPOINT_URL
    assert seen[0].headers["x-api-key"] == "secret"
    assert seen[0].headers["x-keenable-title"] == "my-app"


@pytest.mark.asyncio
@pytest.mark.parametrize(("count", "expected"), [(0, 1), (200, 50)])
async def test_count_is_clamped(monkeypatch, count, expected):
    seen: list[httpx.Request] = []
    _install(monkeypatch, {"results": []}, seen)

    await search_keenable("query", count)

    assert json.loads(seen[0].content)["max_results"] == expected


@pytest.mark.asyncio
async def test_filter_list(monkeypatch):
    _install(monkeypatch, PAYLOAD, [])

    results = await search_keenable("query", 5, filter_list=["example.org"])

    assert [r.link for r in results] == ["https://docs.example.org/b"]


@pytest.mark.asyncio
async def test_endpoint_url_override(monkeypatch):
    seen: list[httpx.Request] = []
    _install(monkeypatch, {"results": []}, seen)

    await search_keenable("query", 5, endpoint_url="http://localhost:9000/v1/search/public")

    assert str(seen[0].url) == "http://localhost:9000/v1/search/public"


@pytest.mark.asyncio
async def test_malformed_endpoint_url_raises():
    with pytest.raises(ValueError, match="keenable"):
        await search_keenable("query", 5, endpoint_url="/v1/search")


@pytest.mark.asyncio
async def test_http_error_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limited"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "web_search.providers.keenable.httpx.AsyncClient",
        lambda *a, **k: _RealAsyncClient(transport=transport),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await search_keenable("query", 5)
