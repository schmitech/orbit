import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from anthropic.types.text_block import TextBlock
from anthropic.types.citations_web_search_result_location import CitationsWebSearchResultLocation

from ai_services.implementations.inference.anthropic_inference_service import AnthropicInferenceService


def _make_citation(url: str, title: str):
    return CitationsWebSearchResultLocation(
        type="web_search_result_location",
        url=url,
        title=title,
        cited_text="...",
        encrypted_index="idx",
    )


class _FakeMessage:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_params = None

    async def create(self, **params):
        self.last_params = params
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _make_service():
    service = AnthropicInferenceService({
        "inference": {"anthropic": {"api_key": "test-key", "model": "claude-sonnet-4-6"}}
    })
    service.initialized = True
    return service


@pytest.mark.asyncio
async def test_generate_appends_sources_when_citations_present():
    text = "Ottawa is partly sunny today."
    content = [TextBlock(type="text", text=text, citations=[
        _make_citation("https://weather.gc.ca/ottawa", "Environment Canada"),
        _make_citation("https://weather.gc.ca/ottawa", "Environment Canada"),  # duplicate
        _make_citation("https://accuweather.com/ottawa", "AccuWeather"),
    ])]
    service = _make_service()
    service.client = _FakeClient(_FakeMessage(content))

    result = await service.generate("search the web for ottawa weather", web_search=True)

    assert text in result
    assert "**Sources:**" in result
    assert "[Environment Canada](https://weather.gc.ca/ottawa)" in result
    assert "[AccuWeather](https://accuweather.com/ottawa)" in result
    assert result.count("weather.gc.ca") == 1


@pytest.mark.asyncio
async def test_generate_no_sources_when_no_citations():
    text = "Ottawa is partly sunny today."
    content = [TextBlock(type="text", text=text, citations=None)]
    service = _make_service()
    service.client = _FakeClient(_FakeMessage(content))

    result = await service.generate("search the web for ottawa weather", web_search=True)

    assert result == text
    assert "Sources" not in result


@pytest.mark.asyncio
async def test_web_search_request_includes_tool():
    text = "Ottawa is partly sunny today."
    content = [TextBlock(type="text", text=text, citations=[
        _make_citation("https://weather.gc.ca/ottawa", "Environment Canada"),
    ])]
    service = _make_service()
    service.client = _FakeClient(_FakeMessage(content))

    await service.generate("search the web for ottawa weather", web_search=True)

    sent_params = service.client.messages.last_params
    assert sent_params["tools"] == [{"type": "web_search_20250305", "name": "web_search"}]


@pytest.mark.asyncio
async def test_generate_without_web_search_omits_tools():
    text = "Just a normal reply."
    content = [TextBlock(type="text", text=text, citations=None)]
    service = _make_service()
    service.client = _FakeClient(_FakeMessage(content))

    result = await service.generate("hello")

    assert result == text
    sent_params = service.client.messages.last_params
    assert "tools" not in sent_params
