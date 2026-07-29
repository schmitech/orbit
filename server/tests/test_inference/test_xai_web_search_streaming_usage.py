"""
Regression test: xAI's streamed web-search branch (generate_stream(...,
web_search=True)) must capture usage from the "response.completed" event
and report it through usage_sink, mirroring the OpenAI implementation.

Prior to this fix the branch returned after yielding text/sources without
ever reading final_response.usage, so total_tokens/cost/reasoning_tokens
were always unreported for xAI streamed web-search requests.
"""

import sys
import os
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ai_services.implementations.inference.xai_inference_service import XAIInferenceService


class _FakeResponses:
    def __init__(self, events):
        self._events = events
        self.last_params = None

    async def create(self, **params):
        self.last_params = params

        async def _iter():
            for event in self._events:
                yield event

        return _iter()


class _FakeClient:
    def __init__(self, events):
        self.responses = _FakeResponses(events)


def _make_service(events):
    service = XAIInferenceService({
        "inference": {"xai": {"api_key": "test-key", "model": "grok-4.3"}}
    })
    service.initialized = True
    service.client = _FakeClient(events)
    return service


def _completed_event(input_tokens, output_tokens, reasoning_tokens=None):
    usage_kwargs = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if reasoning_tokens is not None:
        usage_kwargs["output_tokens_details"] = SimpleNamespace(reasoning_tokens=reasoning_tokens)
    return SimpleNamespace(
        type="response.completed",
        response=SimpleNamespace(usage=SimpleNamespace(**usage_kwargs)),
    )


@pytest.mark.asyncio
class TestXAIWebSearchStreamingUsage:
    async def test_reports_usage_from_completed_event(self):
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="Hello"),
            SimpleNamespace(type="response.output_text.delta", delta=" world"),
            _completed_event(input_tokens=42, output_tokens=8),
        ]
        service = _make_service(events)
        usage_sink = {}

        chunks = [
            c async for c in service.generate_stream(
                "prompt", messages=[{"role": "user", "content": "prompt"}],
                web_search=True, usage_sink=usage_sink,
            )
        ]

        assert chunks == ["Hello", " world"]
        assert usage_sink["reported"] is True
        assert usage_sink["prompt_tokens"] == 42
        assert usage_sink["completion_tokens"] == 8
        assert usage_sink["total_tokens"] == 50

    async def test_reports_reasoning_tokens_when_present(self):
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="answer"),
            _completed_event(input_tokens=10, output_tokens=30, reasoning_tokens=12),
        ]
        service = _make_service(events)
        usage_sink = {}

        [c async for c in service.generate_stream(
            "prompt", messages=[{"role": "user", "content": "prompt"}],
            web_search=True, usage_sink=usage_sink,
        )]

        assert usage_sink["reasoning_tokens"] == 12
        assert usage_sink["completion_tokens"] == 30  # already includes reasoning; not double-counted

    async def test_no_completed_event_leaves_usage_unreported(self):
        """If the stream never emits response.completed (e.g. cut short), usage
        must stay unreported rather than silently defaulting to zero."""
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="partial"),
        ]
        service = _make_service(events)
        usage_sink = {}

        [c async for c in service.generate_stream(
            "prompt", messages=[{"role": "user", "content": "prompt"}],
            web_search=True, usage_sink=usage_sink,
        )]

        assert usage_sink == {}

    async def test_annotations_and_usage_both_captured(self):
        """Sources formatting and usage reporting are independent branches off
        the same response.completed event — verify neither one regresses the other."""
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="answer"),
            SimpleNamespace(
                type="response.output_text.annotation.added",
                annotation=SimpleNamespace(url="https://example.com", title="Example"),
            ),
            _completed_event(input_tokens=5, output_tokens=5),
        ]
        service = _make_service(events)
        service._format_url_citations = lambda annotations: "\n\nSOURCES" if annotations else ""
        usage_sink = {}

        chunks = [
            c async for c in service.generate_stream(
                "prompt", messages=[{"role": "user", "content": "prompt"}],
                web_search=True, usage_sink=usage_sink,
            )
        ]

        assert chunks == ["answer", "\n\nSOURCES"]
        assert usage_sink["reported"] is True
        assert usage_sink["total_tokens"] == 10
