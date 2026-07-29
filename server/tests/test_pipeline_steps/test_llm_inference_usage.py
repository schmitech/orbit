"""
Tests for token-usage plumbing in LLMInferenceStep: context.metadata["usage"]
gets populated from generate_tracked()/generate_stream_tracked(), pricing is
applied when available, and legacy providers that only implement
generate()/generate_stream() still work (delegating through the default
LLMProvider.generate_tracked, which never forwards usage_sink to them).
"""

from unittest.mock import MagicMock

import pytest

from inference.pipeline.base import ProcessingContext
from inference.pipeline.providers.llm_provider import LLMProvider
from inference.pipeline.steps.llm_inference import LLMInferenceStep
from services.pricing_service import PricingService


def _make_container(llm_provider, pricing_service=None):
    services = {"llm_provider": llm_provider}
    if pricing_service is not None:
        services["pricing_service"] = pricing_service
    container = MagicMock()
    container.has.side_effect = lambda key: key in services
    container.get.side_effect = lambda key: services[key]
    container.get_or_none.side_effect = lambda key: services.get(key)
    return container


def _make_context(**overrides):
    ctx = ProcessingContext(message="hello", adapter_name="test-adapter")
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class TrackedFakeProvider(LLMProvider):
    """A provider that supports usage tracking, mirroring UnifiedProviderAdapter."""

    def __init__(self, prompt_tokens=100, completion_tokens=20, reasoning_tokens=None):
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._reasoning_tokens = reasoning_tokens

    async def initialize(self, clock_service=None):
        pass

    async def generate(self, prompt, **kwargs):
        return "response"

    async def generate_stream(self, prompt, **kwargs):
        yield "response"

    async def generate_tracked(self, prompt, usage_sink=None, **kwargs):
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "reasoning_tokens": self._reasoning_tokens,
                "model": "gpt-4o-mini",
                "provider": "openai",
                "reported": True,
            })
        return "response"

    async def generate_stream_tracked(self, prompt, usage_sink=None, **kwargs):
        if usage_sink is not None:
            usage_sink.update({
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "reasoning_tokens": self._reasoning_tokens,
                "model": "gpt-4o-mini",
                "provider": "openai",
                "reported": True,
            })
        yield "response"

    async def close(self):
        pass

    async def validate_config(self):
        return True


class LegacyFakeProvider(LLMProvider):
    """Only implements generate()/generate_stream() — the pre-migration shape."""

    async def initialize(self, clock_service=None):
        pass

    async def generate(self, prompt, **kwargs):
        assert "usage_sink" not in kwargs, "usage_sink must never reach a legacy provider"
        return "legacy response"

    async def generate_stream(self, prompt, **kwargs):
        assert "usage_sink" not in kwargs, "usage_sink must never reach a legacy provider"
        yield "legacy response"

    async def close(self):
        pass

    async def validate_config(self):
        return True


def _pricing_service():
    return PricingService({
        "pricing": {
            "providers": {
                "openai": {"gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60}},
            },
        }
    })


@pytest.mark.unit
@pytest.mark.asyncio
class TestLLMInferenceStepUsage:
    async def test_non_stream_records_usage_and_cost(self):
        provider = TrackedFakeProvider(prompt_tokens=1_000_000, completion_tokens=0)
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        result = await step.process(context)

        usage = result.metadata["usage"]
        assert usage["reported"] is True
        assert usage["prompt_tokens"] == 1_000_000
        assert usage["cost_usd"] == pytest.approx(0.15)
        assert usage["pricing_source"] == "exact"

    async def test_reasoning_tokens_passed_through_when_provider_reports_it(self):
        """reasoning_tokens is informational (already folded into
        completion_tokens for cost) but must still reach context.metadata."""
        provider = TrackedFakeProvider(prompt_tokens=100, completion_tokens=50, reasoning_tokens=30)
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        result = await step.process(context)

        assert result.metadata["usage"]["reasoning_tokens"] == 30

    async def test_reasoning_tokens_absent_when_provider_does_not_report_it(self):
        provider = TrackedFakeProvider(prompt_tokens=100, completion_tokens=50)
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        result = await step.process(context)

        assert result.metadata["usage"]["reasoning_tokens"] is None

    async def test_stream_records_usage_after_generator_exhausted(self):
        provider = TrackedFakeProvider(prompt_tokens=500, completion_tokens=500)
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        chunks = [c async for c in step.process_stream(context)]

        assert chunks == ["response"]
        usage = context.metadata["usage"]
        assert usage["reported"] is True
        assert usage["total_tokens"] == 1000

    async def test_no_pricing_service_yields_none_cost_not_zero(self):
        provider = TrackedFakeProvider(prompt_tokens=100, completion_tokens=100)
        container = _make_container(provider, pricing_service=None)
        step = LLMInferenceStep(container)
        context = _make_context()

        result = await step.process(context)

        usage = result.metadata["usage"]
        assert usage["reported"] is True
        assert usage["cost_usd"] is None

    async def test_legacy_provider_without_tracked_methods_still_works(self):
        """
        Regression guard: LLMProvider.generate_tracked/generate_stream_tracked
        default to plain delegation for providers that only implement
        generate()/generate_stream() — usage_sink must never leak into them
        (most underlying service implementations do `params.update(kwargs)`
        straight into the provider SDK and would 400 on an unknown kwarg).
        """
        provider = LegacyFakeProvider()
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        result = await step.process(context)

        assert result.response == "legacy response"
        usage = result.metadata["usage"]
        assert usage["reported"] is False
        assert usage["cost_usd"] is None
        assert usage["pricing_source"] == "unreported"

    async def test_legacy_provider_streaming_still_works(self):
        provider = LegacyFakeProvider()
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()

        chunks = [c async for c in step.process_stream(context)]

        assert chunks == ["legacy response"]
        assert context.metadata["usage"]["reported"] is False

    async def test_cancelled_stream_does_not_record_usage(self):
        """A cancelled stream never sees the final usage chunk; must stay
        unreported rather than reporting a zero/partial count."""
        provider = TrackedFakeProvider(prompt_tokens=100, completion_tokens=100)
        container = _make_container(provider, pricing_service=_pricing_service())
        step = LLMInferenceStep(container)
        context = _make_context()
        context.is_cancelled = lambda: True

        chunks = [c async for c in step.process_stream(context)]

        assert chunks == []
        assert "usage" not in context.metadata
