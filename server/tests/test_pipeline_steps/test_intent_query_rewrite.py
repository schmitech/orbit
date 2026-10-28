"""
Tests for server/inference/pipeline/steps/intent_query_rewrite.py — the
follow-up query rewriting helper invoked by ContextRetrievalStep before an
intent retriever's template matching.

    venv/bin/python -m pytest server/tests/test_pipeline_steps/test_intent_query_rewrite.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from inference.pipeline.steps import intent_query_rewrite as rewrite_mod
from services import intent_followup_state as followup_state


@pytest.fixture(autouse=True)
def _reset_store():
    followup_state._last_turn.clear()
    yield
    followup_state._last_turn.clear()


def _make_container(llm_provider=None, template=None):
    if template is None:
        template = {
            'template': "Prev: {previous_query} ({previous_parameters})\nNew: {message}\nStandalone:",
            'max_tokens': 150,
            'temperature': 0.1,
        }
    container = MagicMock()
    container.has.return_value = False  # no adapter_manager -> falls back to global llm_provider
    container.get_or_none.side_effect = lambda key: {
        'llm_provider': llm_provider,
        'config': {'rewriters': {'intent_query': template}},
    }.get(key)
    return container


class TestNoLastTurn:
    @pytest.mark.asyncio
    async def test_returns_message_unchanged_without_llm_call(self):
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock()
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(
            container, "adapter-a", "sess-1", "What about Ottawa",
        )

        assert result == "What about Ottawa"
        llm_provider.generate_tracked.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_session_id_returns_message_unchanged(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        container = _make_container(llm_provider=MagicMock())

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", None, "What about Ottawa")
        assert result == "What about Ottawa"


class TestRewriteCall:
    @pytest.mark.asyncio
    async def test_calls_llm_and_returns_rewritten_text(self):
        followup_state.store_last_turn(
            "adapter-a", "sess-1",
            {"effective_query": "How many customers bought in Toronto", "parameters": {"city": "Toronto"}},
        )
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="How many customers bought in Ottawa")
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(
            container, "adapter-a", "sess-1", "What about Ottawa",
        )

        assert result == "How many customers bought in Ottawa"
        llm_provider.generate_tracked.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_strips_surrounding_quotes(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value='"How many customers bought in Ottawa"')
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "How many customers bought in Ottawa"

    @pytest.mark.asyncio
    async def test_passes_usage_sink_through(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="Ottawa")
        container = _make_container(llm_provider=llm_provider)
        sink = {}

        await rewrite_mod.maybe_rewrite_followup_query(
            container, "adapter-a", "sess-1", "what about Ottawa", usage_sink=sink,
        )

        _, kwargs = llm_provider.generate_tracked.call_args
        assert kwargs.get("usage_sink") is sink


class TestFallbackOnFailure:
    @pytest.mark.asyncio
    async def test_no_llm_provider_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        container = _make_container(llm_provider=None)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_empty_llm_output_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="   ")
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_oversized_output_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="x" * 1000)
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_multiline_output_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="line one\nline two")
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(side_effect=RuntimeError("boom"))
        container = _make_container(llm_provider=llm_provider)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_message(self, monkeypatch):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)
            return "too late"

        llm_provider = MagicMock()
        llm_provider.generate_tracked = _hang
        container = _make_container(llm_provider=llm_provider)
        monkeypatch.setattr(rewrite_mod, "_REWRITE_TIMEOUT_SECONDS", 0.05)

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"

    @pytest.mark.asyncio
    async def test_missing_template_falls_back_to_message(self):
        followup_state.store_last_turn("adapter-a", "sess-1", {"effective_query": "Toronto", "parameters": {}})
        llm_provider = MagicMock()
        llm_provider.generate_tracked = AsyncMock(return_value="Ottawa")
        container = _make_container(llm_provider=llm_provider, template={})

        result = await rewrite_mod.maybe_rewrite_followup_query(container, "adapter-a", "sess-1", "what about Ottawa")
        assert result == "what about Ottawa"
        llm_provider.generate_tracked.assert_not_called()
