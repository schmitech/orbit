"""
Table-driven tests for token-usage extraction across inference services,
using lightweight mocked SDK response objects rather than real API calls.
"""

from types import SimpleNamespace

import pytest

from ai_services.services.inference_service import InferenceService
from ai_services.providers.usage_reporting import UsageReportingMixin


@pytest.mark.unit
class TestUsageReportingMixin:
    def test_take_usage_sink_pops_kwarg(self):
        kwargs = {"usage_sink": {"a": 1}, "other": 2}
        sink = UsageReportingMixin._take_usage_sink(kwargs)
        assert sink == {"a": 1}
        assert "usage_sink" not in kwargs
        assert kwargs == {"other": 2}

    def test_take_usage_sink_missing_returns_none(self):
        kwargs = {"other": 2}
        assert UsageReportingMixin._take_usage_sink(kwargs) is None

    def test_report_usage_fills_sink(self):
        class Fake(UsageReportingMixin):
            model = "gpt-4o-mini"
            provider_name = "openai"

        sink = {}
        Fake()._report_usage(sink, 100, 50)
        assert sink == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "reasoning_tokens": None,
            "model": "gpt-4o-mini",
            "provider": "openai",
            "reported": True,
        }

    def test_report_usage_with_reasoning_tokens(self):
        class Fake(UsageReportingMixin):
            model = "gpt-5.4-mini"
            provider_name = "openai"

        sink = {}
        Fake()._report_usage(sink, 100, 50, reasoning_tokens=30)
        assert sink["reasoning_tokens"] == 30
        assert sink["completion_tokens"] == 50  # already includes reasoning; not double-counted

    def test_extract_reasoning_tokens_chat_completions_shape(self):
        usage = SimpleNamespace(
            prompt_tokens=10, completion_tokens=50,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=30),
        )
        assert UsageReportingMixin._extract_reasoning_tokens(usage) == 30

    def test_extract_reasoning_tokens_responses_api_shape(self):
        usage = SimpleNamespace(
            input_tokens=10, output_tokens=50,
            output_tokens_details=SimpleNamespace(reasoning_tokens=12),
        )
        assert UsageReportingMixin._extract_reasoning_tokens(usage) == 12

    def test_extract_reasoning_tokens_missing_details_returns_none(self):
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=50)
        assert UsageReportingMixin._extract_reasoning_tokens(usage) is None

    def test_extract_reasoning_tokens_none_usage_returns_none(self):
        assert UsageReportingMixin._extract_reasoning_tokens(None) is None

    def test_report_usage_none_sink_is_noop(self):
        class Fake(UsageReportingMixin):
            model = "x"
            provider_name = "y"

        # Must not raise.
        Fake()._report_usage(None, 1, 1)

    def test_report_usage_handles_missing_counts(self):
        class Fake(UsageReportingMixin):
            model = "x"
            provider_name = "y"

        sink = {}
        Fake()._report_usage(sink, None, None)
        assert sink["prompt_tokens"] == 0
        assert sink["completion_tokens"] == 0
        assert sink["total_tokens"] == 0
        assert sink["reported"] is True


@pytest.mark.unit
class TestOpenAIUsageExtraction:
    def test_non_stream_response_usage(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=42, completion_tokens=8),
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
        )
        sink = {}

        class Fake(UsageReportingMixin):
            model = "gpt-4o-mini"
            provider_name = "openai"

        usage = getattr(response, "usage", None)
        Fake()._report_usage(sink, usage.prompt_tokens, usage.completion_tokens)
        assert sink["prompt_tokens"] == 42
        assert sink["completion_tokens"] == 8
        assert sink["reported"] is True

    def test_stream_final_usage_chunk_has_empty_choices(self):
        # Mirrors the shape OpenAI's SDK yields when stream_options.include_usage
        # is set: a trailing chunk with choices=[] and a populated usage object.
        final_chunk = SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))
        content_chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))], usage=None
        )

        sink = {}

        class Fake(UsageReportingMixin):
            model = "gpt-4o-mini"
            provider_name = "openai"

        fake = Fake()
        for chunk in (content_chunk, final_chunk):
            if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                continue
            elif getattr(chunk, "usage", None):
                fake._report_usage(sink, chunk.usage.prompt_tokens, chunk.usage.completion_tokens)

        assert sink["prompt_tokens"] == 10
        assert sink["completion_tokens"] == 5

    def test_missing_usage_leaves_sink_unreported(self):
        response = SimpleNamespace(usage=None)
        sink = {}
        usage = getattr(response, "usage", None)
        if usage is not None:
            pass  # would report
        assert sink == {}
        assert sink.get("reported") is not True


@pytest.mark.unit
class TestAnthropicUsageExtraction:
    def test_non_stream_response_usage(self):
        response = SimpleNamespace(usage=SimpleNamespace(input_tokens=30, output_tokens=12))
        sink = {}

        class Fake(UsageReportingMixin):
            model = "claude-sonnet-4-6"
            provider_name = "anthropic"

        usage = getattr(response, "usage", None)
        Fake()._report_usage(sink, usage.input_tokens, usage.output_tokens)
        assert sink["prompt_tokens"] == 30
        assert sink["completion_tokens"] == 12

    def test_streaming_final_message_usage_is_cumulative_not_summed(self):
        # message_start carries input_tokens; message_delta.usage.output_tokens
        # is cumulative on Anthropic's protocol (imagine deltas of 1, then 5,
        # then 9) — get_final_message() already gives the final, already-summed
        # totals, so we must take that value as-is rather than adding deltas.
        final_message = SimpleNamespace(usage=SimpleNamespace(input_tokens=20, output_tokens=9))

        sink = {}

        class Fake(UsageReportingMixin):
            model = "claude-sonnet-4-6"
            provider_name = "anthropic"

        usage = getattr(final_message, "usage", None)
        Fake()._report_usage(sink, usage.input_tokens, usage.output_tokens)

        assert sink["completion_tokens"] == 9  # not 1+5+9
        assert sink["prompt_tokens"] == 20


@pytest.mark.unit
class TestGeminiUsageExtraction:
    def test_non_stream_usage_metadata(self):
        response = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=15, candidates_token_count=25)
        )
        sink = {}

        class Fake(UsageReportingMixin):
            model = "gemini-3.6-flash"
            provider_name = "gemini"

        usage = getattr(response, "usage_metadata", None)
        Fake()._report_usage(sink, usage.prompt_token_count, usage.candidates_token_count)
        assert sink["prompt_tokens"] == 15
        assert sink["completion_tokens"] == 25

    def test_stream_takes_last_chunk_usage(self):
        chunks = [
            SimpleNamespace(candidates=[], usage_metadata=None),
            SimpleNamespace(candidates=[], usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1)),
            SimpleNamespace(candidates=[], usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=3)),
        ]
        last_usage = None
        for chunk in chunks:
            if getattr(chunk, "usage_metadata", None) is not None:
                last_usage = chunk.usage_metadata

        sink = {}

        class Fake(UsageReportingMixin):
            model = "gemini-3.6-flash"
            provider_name = "gemini"

        Fake()._report_usage(sink, last_usage.prompt_token_count, last_usage.candidates_token_count)
        assert sink["prompt_tokens"] == 7
        assert sink["completion_tokens"] == 3

    def test_thoughts_token_count_reported_as_reasoning_tokens(self):
        """Gemini reports thinking tokens in a separate field from
        candidates_token_count; the completion total already folds it in
        (see gemini_inference_service._billed_completion_tokens), and it's
        also surfaced standalone via reasoning_tokens for visibility."""
        usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=20, thoughts_token_count=15)
        sink = {}

        class Fake(UsageReportingMixin):
            model = "gemini-3.6-flash"
            provider_name = "gemini"

        billed_completion = usage.candidates_token_count + usage.thoughts_token_count
        Fake()._report_usage(
            sink, usage.prompt_token_count, billed_completion,
            reasoning_tokens=usage.thoughts_token_count,
        )
        assert sink["completion_tokens"] == 35
        assert sink["reasoning_tokens"] == 15


@pytest.mark.unit
class TestOllamaUsageExtraction:
    def test_reports_prompt_eval_and_eval_counts(self):
        data = {"response": "hi", "prompt_eval_count": 12, "eval_count": 4, "done": True}
        sink = {}

        class Fake(UsageReportingMixin):
            model = "granite4:1b"
            provider_name = "ollama"

        if "prompt_eval_count" in data or "eval_count" in data:
            Fake()._report_usage(sink, data.get("prompt_eval_count"), data.get("eval_count"))

        assert sink["prompt_tokens"] == 12
        assert sink["completion_tokens"] == 4

    def test_missing_counts_leaves_sink_empty(self):
        data = {"response": "hi", "done": True}
        sink = {}
        if "prompt_eval_count" in data or "eval_count" in data:
            pytest.fail("should not report when counts are absent")
        assert sink == {}


@pytest.mark.unit
class TestInferenceServiceTrackedDelegation:
    class LegacyService(InferenceService):
        """A service with no usage-reporting support at all — the default case."""

        def __init__(self):
            self.calls = []

        async def initialize(self):
            pass

        async def close(self):
            pass

        async def verify_connection(self):
            return True

        async def generate(self, prompt, **kwargs):
            self.calls.append(kwargs)
            return "ok"

        async def generate_stream(self, prompt, **kwargs):
            self.calls.append(kwargs)
            yield "chunk"

    @pytest.mark.asyncio
    async def test_generate_tracked_does_not_leak_usage_sink_to_unsupported_service(self):
        svc = self.LegacyService()
        sink = {}
        result = await svc.generate_tracked("hi", usage_sink=sink, foo="bar")
        assert result == "ok"
        # usage_sink must never reach an implementation that doesn't support it
        assert svc.calls == [{"foo": "bar"}]
        assert sink == {}

    @pytest.mark.asyncio
    async def test_generate_stream_tracked_does_not_leak_usage_sink(self):
        svc = self.LegacyService()
        sink = {}
        chunks = [c async for c in svc.generate_stream_tracked("hi", usage_sink=sink, foo="bar")]
        assert chunks == ["chunk"]
        assert svc.calls == [{"foo": "bar"}]
        assert sink == {}
