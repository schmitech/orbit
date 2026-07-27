import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from openai.types.responses import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText, AnnotationURLCitation

from ai_services.implementations.inference.openai_inference_service import OpenAIInferenceService


def _make_message_output(text: str, citations):
    annotations = [
        AnnotationURLCitation(
            type="url_citation",
            url=url,
            title=title,
            start_index=0,
            end_index=len(text),
        )
        for url, title in citations
    ]
    return ResponseOutputMessage(
        id="msg_1",
        role="assistant",
        status="completed",
        type="message",
        content=[
            ResponseOutputText(
                type="output_text",
                text=text,
                annotations=annotations,
            )
        ],
    )


class _FakeAction:
    def __init__(self, sources):
        self.sources = sources


class _FakeWebSearchCall:
    def __init__(self, sources):
        self.type = "web_search_call"
        self.action = _FakeAction(sources)


class _FakeResponse:
    def __init__(self, output_text, output):
        self.output_text = output_text
        self.output = output


class _FakeResponses:
    def __init__(self, response):
        self._response = response
        self.last_params = None

    async def create(self, **params):
        self.last_params = params
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.responses = _FakeResponses(response)


def _make_service():
    service = OpenAIInferenceService({
        "inference": {"openai": {"api_key": "test-key", "model": "gpt-5.6"}}
    })
    service.initialized = True
    return service


@pytest.mark.asyncio
async def test_generate_appends_sources_when_annotations_present():
    """If the SDK returns url_citation annotations, generate() should append them."""
    text = "Ottawa is partly sunny today."
    output = [_make_message_output(text, [
        ("https://weather.gc.ca/ottawa", "Environment Canada"),
        ("https://weather.gc.ca/ottawa", "Environment Canada"),  # duplicate, should be deduped
        ("https://accuweather.com/ottawa", "AccuWeather"),
    ])]
    response = _FakeResponse(output_text=text, output=output)
    service = _make_service()
    service.client = _FakeClient(response)

    result = await service.generate("search the web for ottawa weather", web_search=True)

    assert text in result
    assert "**Sources:**" in result
    assert "[Environment Canada](https://weather.gc.ca/ottawa)" in result
    assert "[AccuWeather](https://accuweather.com/ottawa)" in result
    # only one Environment Canada line despite two identical annotations
    assert result.count("weather.gc.ca") == 1


@pytest.mark.asyncio
async def test_generate_falls_back_to_action_sources_when_no_annotations():
    """
    Reproduces the reported gpt-5.6 behavior: the message carries zero
    url_citation annotations even though a web_search_call found real pages
    (confirmed against the live API - some models never populate message
    annotations). generate() should fall back to the search call's own
    action.sources instead of returning bare text.
    """
    text = "Ottawa is partly sunny today."
    output = [_make_message_output(text, [])]
    output.insert(0, _FakeWebSearchCall([
        {"type": "url", "url": "https://weather.gc.ca/ottawa"},
        {"type": "api", "url": None, "name": "oai-weather"},  # no-URL source, must be skipped
    ]))
    response = _FakeResponse(output_text=text, output=output)
    service = _make_service()
    service.client = _FakeClient(response)

    result = await service.generate("search the web for ottawa weather", web_search=True)

    assert "**Sources:**" in result
    assert "[weather.gc.ca](https://weather.gc.ca/ottawa)" in result


@pytest.mark.asyncio
async def test_generate_no_sources_when_nothing_citable():
    """A web_search_call whose only source is a URL-less internal API tool (e.g. oai-weather)."""
    text = "Ottawa is partly sunny today."
    output = [_make_message_output(text, [])]
    output.insert(0, _FakeWebSearchCall([{"type": "api", "url": None, "name": "oai-weather"}]))
    response = _FakeResponse(output_text=text, output=output)
    service = _make_service()
    service.client = _FakeClient(response)

    result = await service.generate("search the web for ottawa weather", web_search=True)

    assert result == text
    assert "Sources" not in result


@pytest.mark.asyncio
async def test_web_search_request_includes_sources_param():
    """_build_web_search_params must request web_search_call.action.sources."""
    text = "Ottawa is partly sunny today."
    output = [_make_message_output(text, [("https://weather.gc.ca/ottawa", "Environment Canada")])]
    response = _FakeResponse(output_text=text, output=output)
    service = _make_service()
    service.client = _FakeClient(response)

    await service.generate("search the web for ottawa weather", web_search=True)

    sent_params = service.client.responses.last_params
    assert sent_params["tools"] == [{"type": "web_search"}]
    assert "include" in sent_params
    assert "web_search_call.action.sources" in sent_params["include"]
