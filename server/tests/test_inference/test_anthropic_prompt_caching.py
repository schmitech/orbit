import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

anthropic = pytest.importorskip("anthropic")

from anthropic.types.text_block import TextBlock

from ai_services.implementations.inference.anthropic_inference_service import AnthropicInferenceService


class _FakeMessage:
    def __init__(self, content, stop_reason="end_turn", usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


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
    text = "Hello!"
    service.client = _FakeClient(_FakeMessage([TextBlock(type="text", text=text, citations=None)]))
    return service


@pytest.mark.asyncio
async def test_generate_adds_cache_control_breakpoint_when_prefix_len_given():
    service = _make_service()
    system = "You are ORBIT Assistant.\nCHART RULES...\n"
    tail = "\nIMPORTANT: current time is now."
    messages = [
        {"role": "system", "content": system + tail},
        {"role": "user", "content": "hello"},
    ]

    await service.generate("hello", messages=messages, cache_prefix_len=len(system))

    sent_system = service.client.messages.last_params["system"]
    assert isinstance(sent_system, list)
    assert sent_system[0]["text"] == system
    assert sent_system[0]["cache_control"] == {"type": "ephemeral"}
    assert sent_system[1]["text"] == tail
    assert "cache_control" not in sent_system[1]


@pytest.mark.asyncio
async def test_generate_adds_breakpoint_when_prefix_covers_entire_system_message():
    """No volatile tail (language/clock/RAG all disabled) must still cache."""
    service = _make_service()
    system = "You are ORBIT Assistant.\nCHART RULES...\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "hello"},
    ]

    await service.generate("hello", messages=messages, cache_prefix_len=len(system))

    sent_system = service.client.messages.last_params["system"]
    assert isinstance(sent_system, list)
    assert sent_system == [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


@pytest.mark.asyncio
async def test_generate_uses_plain_string_system_when_no_prefix_len():
    service = _make_service()
    messages = [
        {"role": "system", "content": "You are ORBIT Assistant."},
        {"role": "user", "content": "hello"},
    ]

    await service.generate("hello", messages=messages)

    sent_system = service.client.messages.last_params["system"]
    assert sent_system == "You are ORBIT Assistant."


@pytest.mark.asyncio
async def test_generate_ignores_out_of_range_prefix_len():
    service = _make_service()
    system = "short"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "hello"},
    ]

    await service.generate("hello", messages=messages, cache_prefix_len=999)

    sent_system = service.client.messages.last_params["system"]
    assert sent_system == system


@pytest.mark.asyncio
async def test_cache_prefix_len_never_reaches_provider_kwargs():
    """cache_prefix_len must be consumed, never forwarded raw into the SDK call."""
    service = _make_service()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    await service.generate("hello", messages=messages, cache_prefix_len=1)

    assert "cache_prefix_len" not in service.client.messages.last_params


@pytest.mark.asyncio
async def test_generate_reports_cache_read_tokens_and_total_input_tokens():
    """
    Anthropic's usage.input_tokens excludes cache_read_input_tokens and
    cache_creation_input_tokens (both billed separately) — prompt_tokens
    reported to PricingService must be the sum of all three, with the
    cache-read portion also surfaced separately as cached_prompt_tokens so
    it can be priced at a discount.
    """
    from types import SimpleNamespace

    service = _make_service()
    usage = SimpleNamespace(
        input_tokens=50,
        output_tokens=20,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=30,
    )
    service.client = _FakeClient(
        _FakeMessage([TextBlock(type="text", text="Hello!", citations=None)], usage=usage)
    )
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]

    usage_sink = {}
    await service.generate("hello", messages=messages, usage_sink=usage_sink)

    assert usage_sink["prompt_tokens"] == 980  # 50 + 900 + 30
    assert usage_sink["cached_prompt_tokens"] == 900
    assert usage_sink["completion_tokens"] == 20
