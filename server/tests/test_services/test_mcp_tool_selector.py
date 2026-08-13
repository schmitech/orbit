#!/usr/bin/env python3
"""
Unit tests for MCPToolSelector (server/services/mcp_tool_selector.py).

Covers: the small-list bypass, embedding-threshold filtering, the
already-called-tool union guarantee, and the no-embedding-provider /
init-failure fallbacks — all without a live provider.
"""

import os
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from services.mcp_tool_selector import MCPToolSelector, _cosine


class _FakeEmbeddingClient:
    """Deterministic embeddings driven by an explicit {text: vector} table.

    Text not in the table maps to a zero vector, which _cosine scores as
    0.0 against anything (including another zero vector) — exercises the
    below-threshold filtering path without accidentally self-matching.
    """

    def __init__(self, table):
        self.table = table
        self.initialized = True

    def _vec(self, text):
        return self.table.get(text, [0.0, 0.0, 0.0])

    async def initialize(self):
        self.initialized = True

    async def embed_query(self, text):
        return self._vec(text)

    async def embed_documents(self, texts):
        return [self._vec(t) for t in texts]


class _FakeAdapterManager:
    def __init__(self, adapter_configs=None, embedding_client=None):
        self._configs = adapter_configs or {}
        self._embedding_client = embedding_client

    def get_adapter_config(self, adapter_name):
        return self._configs.get(adapter_name, {})

    async def get_overridden_embedding(self, provider_name):
        return self._embedding_client


def _tool(name, description=""):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {}}}


def _config(threshold=0.3, max_tools=2, enabled=True, embedding_provider="fake"):
    return {
        "mcp_clients": {
            "tool_selection": {
                "enabled": enabled,
                "max_tools": max_tools,
                "embedding_threshold": threshold,
            }
        },
        "embedding": {"provider": embedding_provider},
    }


@pytest.fixture(autouse=True)
def _reset_selector_caches():
    """Class-level caches persist across instances by design (see the
    module docstring) — reset them between tests so one test's fake
    embedding client/index can't leak into the next."""
    MCPToolSelector._embedding_clients = {}
    MCPToolSelector._phrase_cache = {}
    MCPToolSelector._warned_no_provider = False
    yield
    MCPToolSelector._embedding_clients = {}
    MCPToolSelector._phrase_cache = {}
    MCPToolSelector._warned_no_provider = False


class TestCosine:
    def test_identical_vectors_score_one(self):
        assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_zero_vector_scores_zero(self):
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


@pytest.mark.asyncio
class TestMCPToolSelectorBypass:
    async def test_returns_unchanged_when_tool_count_at_or_under_cap(self):
        tools = [_tool("srv__a"), _tool("srv__b")]
        selector = MCPToolSelector(_config(max_tools=2), _FakeAdapterManager())
        result = await selector.select_tools("hello", tools, "my-adapter")
        assert result == tools

    async def test_returns_unchanged_when_disabled(self):
        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        selector = MCPToolSelector(_config(max_tools=1, enabled=False), _FakeAdapterManager())
        result = await selector.select_tools("hello", tools, "my-adapter")
        assert result == tools

    async def test_returns_unchanged_for_empty_message(self):
        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        selector = MCPToolSelector(_config(max_tools=1), _FakeAdapterManager())
        result = await selector.select_tools("   ", tools, "my-adapter")
        assert result == tools

    async def test_returns_unchanged_when_no_embedding_provider_configured(self):
        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        config = _config(max_tools=1)
        config["embedding"] = {}  # no provider configured anywhere
        selector = MCPToolSelector(config, _FakeAdapterManager())
        result = await selector.select_tools("hello", tools, "my-adapter")
        assert result == tools

    async def test_returns_unchanged_when_embedding_client_init_fails(self):
        class _BrokenClient:
            initialized = False

            async def initialize(self):
                raise RuntimeError("boom")

        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        adapter_manager = _FakeAdapterManager(embedding_client=_BrokenClient())
        selector = MCPToolSelector(_config(max_tools=1), adapter_manager)
        result = await selector.select_tools("hello", tools, "my-adapter")
        assert result == tools


@pytest.mark.asyncio
class TestMCPToolSelectorFiltering:
    async def test_keeps_only_tools_above_threshold(self):
        tools = [
            _tool("srv__weather", "get current weather for a city"),
            _tool("srv__stock", "look up a stock price"),
            _tool("srv__unrelated_a"),
            _tool("srv__unrelated_b"),
        ]
        table = {
            "what's the weather in paris": [1.0, 0.0, 0.0],
            "srv__weather: get current weather for a city": [1.0, 0.0, 0.0],
            "srv__stock: look up a stock price": [0.0, 1.0, 0.0],
        }
        client = _FakeEmbeddingClient(table)
        adapter_manager = _FakeAdapterManager(embedding_client=client)
        selector = MCPToolSelector(_config(max_tools=2, threshold=0.5), adapter_manager)

        result = await selector.select_tools(
            "what's the weather in paris", tools, "my-adapter"
        )

        names = {t["function"]["name"] for t in result}
        assert names == {"srv__weather"}

    async def test_already_called_tool_is_unioned_in_even_below_threshold(self):
        tools = [
            _tool("srv__weather", "get current weather for a city"),
            _tool("srv__stock", "look up a stock price"),
            _tool("srv__unrelated"),
        ]
        table = {
            "what's the weather in paris": [1.0, 0.0, 0.0],
            "srv__weather: get current weather for a city": [1.0, 0.0, 0.0],
        }
        client = _FakeEmbeddingClient(table)
        adapter_manager = _FakeAdapterManager(embedding_client=client)
        selector = MCPToolSelector(_config(max_tools=1, threshold=0.5), adapter_manager)

        context_messages = [
            {"role": "assistant", "tool_calls": [{"function": {"name": "srv__stock"}}]},
        ]
        result = await selector.select_tools(
            "what's the weather in paris", tools, "my-adapter",
            context_messages=context_messages,
        )

        names = {t["function"]["name"] for t in result}
        assert "srv__weather" in names  # top-scored, above threshold
        assert "srv__stock" in names    # already called — unioned in regardless of score
        assert "srv__unrelated" not in names

    async def test_already_called_tool_from_stored_history_is_unioned_in(self):
        """
        A tool called in a *stored* (reloaded from history) turn is recorded
        as mcp_tools_used, not tool_calls — ChatHistoryService.get_context_messages()
        only reconstructs role/content plus this field, never a raw
        tool_calls list (see response_processor.py / chat_history_service.py).
        The union guarantee must still hold against that shape.
        """
        tools = [
            _tool("srv__weather", "get current weather for a city"),
            _tool("srv__stock", "look up a stock price"),
            _tool("srv__unrelated"),
        ]
        table = {
            "what's the weather in paris": [1.0, 0.0, 0.0],
            "srv__weather: get current weather for a city": [1.0, 0.0, 0.0],
        }
        client = _FakeEmbeddingClient(table)
        adapter_manager = _FakeAdapterManager(embedding_client=client)
        selector = MCPToolSelector(_config(max_tools=1, threshold=0.5), adapter_manager)

        context_messages = [
            {"role": "user", "content": "look up AAPL"},
            {"role": "assistant", "content": "It's $150.", "mcp_tools_used": ["srv__stock"]},
        ]
        result = await selector.select_tools(
            "what's the weather in paris", tools, "my-adapter",
            context_messages=context_messages,
        )

        names = {t["function"]["name"] for t in result}
        assert "srv__weather" in names  # top-scored, above threshold
        assert "srv__stock" in names    # already called (stored history) — unioned in
        assert "srv__unrelated" not in names

    async def test_falls_back_to_full_list_when_nothing_survives(self):
        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        client = _FakeEmbeddingClient({})  # everything maps to the same 'unrelated' vector
        adapter_manager = _FakeAdapterManager(embedding_client=client)
        selector = MCPToolSelector(_config(max_tools=1, threshold=0.9), adapter_manager)

        result = await selector.select_tools("hello", tools, "my-adapter")
        assert result == tools

    async def test_adapter_embedding_provider_override_is_used(self):
        tools = [_tool("srv__a"), _tool("srv__b"), _tool("srv__c")]
        client = _FakeEmbeddingClient({
            "hello": [1.0, 0.0, 0.0],
            "srv__a": [1.0, 0.0, 0.0],
        })
        adapter_manager = _FakeAdapterManager(
            adapter_configs={"my-adapter": {"embedding_provider": "adapter-specific"}},
            embedding_client=client,
        )
        config = _config(max_tools=1, threshold=0.5, embedding_provider="global-default")
        selector = MCPToolSelector(config, adapter_manager)

        result = await selector.select_tools("hello", tools, "my-adapter")
        names = {t["function"]["name"] for t in result}
        assert names == {"srv__a"}
