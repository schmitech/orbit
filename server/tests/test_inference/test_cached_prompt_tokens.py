"""
Regression tests for Phase 2c: providers that support automatic prompt
caching (DeepSeek, xAI) must surface the cached-token subset through
usage_sink as cached_prompt_tokens, so PricingService can price it at a
discount when one is configured (see cached_input_per_1m in pricing.yaml).
"""

import sys
import os
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ai_services.implementations.inference.deepseek_inference_service import DeepSeekInferenceService
from ai_services.implementations.inference.xai_inference_service import XAIInferenceService


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    async def create(self, **params):
        return self._response


class _FakeChatClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response))


def _chat_response(content, usage):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


@pytest.mark.asyncio
class TestDeepSeekCachedPromptTokens:
    async def test_generate_reports_cache_hit_tokens(self):
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20, prompt_cache_hit_tokens=80)
        service = DeepSeekInferenceService({"inference": {"deepseek": {"api_key": "k", "model": "deepseek-chat"}}})
        service.initialized = True
        service.client = _FakeChatClient(_chat_response("hi", usage))

        usage_sink = {}
        await service.generate("hello", usage_sink=usage_sink)

        assert usage_sink["cached_prompt_tokens"] == 80
        assert usage_sink["prompt_tokens"] == 100

    async def test_generate_without_cache_fields_reports_none(self):
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        service = DeepSeekInferenceService({"inference": {"deepseek": {"api_key": "k", "model": "deepseek-chat"}}})
        service.initialized = True
        service.client = _FakeChatClient(_chat_response("hi", usage))

        usage_sink = {}
        await service.generate("hello", usage_sink=usage_sink)

        assert usage_sink["cached_prompt_tokens"] is None


@pytest.mark.asyncio
class TestXAICachedPromptTokens:
    async def test_generate_reports_cached_tokens_from_prompt_tokens_details(self):
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
            prompt_tokens_details=SimpleNamespace(cached_tokens=60),
        )
        service = XAIInferenceService({"inference": {"xai": {"api_key": "k", "model": "grok-4.3"}}})
        service.initialized = True
        service.client = _FakeChatClient(_chat_response("hi", usage))

        usage_sink = {}
        await service.generate("hello", usage_sink=usage_sink)

        assert usage_sink["cached_prompt_tokens"] == 60

    async def test_generate_without_prompt_tokens_details_reports_none(self):
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        service = XAIInferenceService({"inference": {"xai": {"api_key": "k", "model": "grok-4.3"}}})
        service.initialized = True
        service.client = _FakeChatClient(_chat_response("hi", usage))

        usage_sink = {}
        await service.generate("hello", usage_sink=usage_sink)

        assert usage_sink["cached_prompt_tokens"] is None

    async def test_web_search_generate_reports_cached_tokens_from_input_tokens_details(self):
        """
        web_search=True routes through the Responses API instead of
        chat.completions; cached tokens are nested under
        input_tokens_details.cached_tokens there, not prompt_tokens_details.
        """
        usage = SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            input_tokens_details=SimpleNamespace(cached_tokens=70),
        )
        response = SimpleNamespace(output_text="answer", usage=usage, output=[])
        service = XAIInferenceService({"inference": {"xai": {"api_key": "k", "model": "grok-4.3"}}})
        service.initialized = True
        service.client = SimpleNamespace(responses=_FakeResponsesCreate(response))

        usage_sink = {}
        await service.generate(
            "hello", messages=[{"role": "user", "content": "hello"}],
            web_search=True, usage_sink=usage_sink,
        )

        assert usage_sink["cached_prompt_tokens"] == 70

    async def test_web_search_generate_stream_reports_cached_tokens(self):
        usage = SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            input_tokens_details=SimpleNamespace(cached_tokens=45),
        )
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="answer"),
            SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=usage)),
        ]
        service = XAIInferenceService({"inference": {"xai": {"api_key": "k", "model": "grok-4.3"}}})
        service.initialized = True
        service.client = SimpleNamespace(responses=_FakeResponsesStream(events))

        usage_sink = {}
        [c async for c in service.generate_stream(
            "hello", messages=[{"role": "user", "content": "hello"}],
            web_search=True, usage_sink=usage_sink,
        )]

        assert usage_sink["cached_prompt_tokens"] == 45


class _FakeResponsesCreate:
    def __init__(self, response):
        self._response = response

    async def create(self, **params):
        return self._response


class _FakeResponsesStream:
    def __init__(self, events):
        self._events = events

    async def create(self, **params):
        async def _iter():
            for event in self._events:
                yield event
        return _iter()
