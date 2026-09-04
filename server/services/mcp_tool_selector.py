"""
MCP Tool Relevance Filter

Cuts the MCP tool schema list down to the ones actually relevant to the
current turn, instead of always sending every tool from every enabled
server. A single large MCP server (e.g. GitHub's, ~70-100 tools) can put
20k-50k tokens of tool schemas on every provider call, re-sent on each
iteration of the tool-calling loop (mcp_tool_loop.run_tool_calling_loop) —
this filters that list once per turn, before the loop starts, and keeps it
fixed for the whole loop.

Single-stage embedding pre-filter only (unlike SkillIntentRouter's
embedding + LLM confirm): a false positive here just means one extra tool
offered to the model, not a wrong action taken, so the cheaper one-stage
approach is enough.
"""

import logging
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _cosine(v1: list[float], v2: list[float]) -> float:
    """Cosine similarity between two vectors; 0.0 when either is a zero vector."""
    a = np.asarray(v1, dtype=float)
    b = np.asarray(v2, dtype=float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class MCPToolSelector:
    """Embedding-based relevance filter for the per-turn MCP tool list."""

    # Shared across every instance/request in this process — tool schemas
    # rarely change, so there's no reason to re-embed them on every call.
    # Keyed by (embedding_provider, frozenset of tool names).
    _embedding_clients: dict[str, Any] = {}
    _phrase_cache: dict[tuple, dict[str, list[float]]] = {}
    _warned_no_provider = False

    def __init__(self, config: dict[str, Any], adapter_manager):
        self.config = config or {}
        self.adapter_manager = adapter_manager

        selection_cfg = ((self.config.get("mcp_clients") or {}).get("tool_selection") or {})
        self.enabled = bool(selection_cfg.get("enabled", True))
        self.max_tools = int(selection_cfg.get("max_tools", 15))
        self.embedding_threshold = float(selection_cfg.get("embedding_threshold", 0.3))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def select_tools(
        self,
        message: Optional[str],
        tools: list[dict[str, Any]],
        adapter_name: Optional[str],
        context_messages: Optional[list[dict[str, Any]]] = None,
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Return the subset of `tools` relevant to this turn, in their original
        order, always including any tool already called earlier in this
        thread. Never raises and never returns fewer tools than the caller
        can safely use — any internal failure, a disabled config, a tool
        count already at or under the cap, or no embedding provider being
        available all fall back to returning `tools` unchanged.
        """
        if not self.enabled or len(tools) <= self.max_tools or not message or not message.strip():
            return tools

        already_called = self._called_tool_names(context_messages)

        try:
            provider = self._resolve_embedding_provider(adapter_name)
            if not provider:
                self._warn_once("no embedding provider configured (adapter embedding_provider or global embedding.provider)")
                return tools
            client = await self._get_embedding_client(provider)
            if client is None:
                return tools

            key = (provider, frozenset(self._tool_name(t) for t in tools))
            phrase_index = self._phrase_cache.get(key)
            if phrase_index is None:
                phrase_index = await self._build_phrase_index(client, tools, usage_sink=usage_sink)
                self._phrase_cache[key] = phrase_index

            if hasattr(client, "embed_query_tracked"):
                local_usage: dict[str, Any] = {}
                query_vec = await client.embed_query_tracked(message, usage_sink=local_usage)
                from ai_services.providers.usage_reporting import accumulate_usage_sink
                accumulate_usage_sink(usage_sink, local_usage)
            else:
                query_vec = await client.embed_query(message)

            scored = []
            for tool in tools:
                vec = phrase_index.get(self._tool_name(tool))
                score = _cosine(query_vec, vec) if vec else 0.0
                scored.append((score, tool))
            scored.sort(key=lambda item: item[0], reverse=True)

            selected_names: set[str] = {
                self._tool_name(tool)
                for score, tool in scored[: self.max_tools]
                if score >= self.embedding_threshold
            }
            # Always union in every tool already called in this thread, even
            # past the cap/threshold — a multi-step task must never lose a
            # tool it is mid-way through using.
            selected_names |= already_called & {self._tool_name(t) for t in tools}

            if not selected_names:
                return tools

            selected = [t for t in tools if self._tool_name(t) in selected_names]
            logger.debug(
                "MCP tool selection: kept %d/%d tools for adapter '%s'",
                len(selected), len(tools), adapter_name,
            )
            return selected
        except Exception as e:
            logger.warning("MCP tool selection failed, falling back to full tool list: %s", e)
            return tools

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_name(tool: dict[str, Any]) -> str:
        return tool.get("function", {}).get("name", "")

    @staticmethod
    def _called_tool_names(context_messages: Optional[list[dict[str, Any]]]) -> set[str]:
        """
        Tool names invoked in prior turns of this thread, so a multi-step
        task in progress never has its tools pulled out from under it.

        Two sources, because the two paths that produce context_messages
        shape this differently:
          - `tool_calls` — OpenAI-format assistant messages, as they exist
            in-memory during a live tool-calling loop (mcp_tool_loop.py).
          - `mcp_tools_used` — a flat list of tool names, as persisted and
            reconstructed by ChatHistoryService for a *stored* session:
            get_context_messages() only reconstructs role/content from the
            database, so response_processor.py separately records which
            tools a turn used into that message's metadata, and
            get_context_messages() surfaces it back here under this key.
            Without this, the union guarantee below silently never fires for
            any ordinary session follow-up, since context_messages loaded
            from storage never carries a `tool_calls` key at all.
        """
        names: set[str] = set()
        for msg in context_messages or []:
            for tc in (msg.get("tool_calls") or []):
                name = (tc.get("function") or {}).get("name")
                if name:
                    names.add(name)
            for name in (msg.get("mcp_tools_used") or []):
                if name:
                    names.add(name)
        return names

    def _resolve_embedding_provider(self, adapter_name: Optional[str]) -> Optional[str]:
        """Adapter's embedding_provider override if set, else the global default."""
        cfg = (self.adapter_manager.get_adapter_config(adapter_name) or {}) if adapter_name else {}
        return cfg.get("embedding_provider") or (self.config.get("embedding") or {}).get("provider")

    async def _get_embedding_client(self, provider: str):
        client = self._embedding_clients.get(provider)
        if client is not None:
            return client
        client = await self.adapter_manager.get_overridden_embedding(provider)
        if client is not None and not getattr(client, "initialized", False):
            try:
                await client.initialize()
            except Exception as e:
                logger.warning("Embedding init failed for MCP tool selection: %s", e)
                return None
        self._embedding_clients[provider] = client
        return client

    async def _build_phrase_index(
        self,
        client,
        tools: list[dict[str, Any]],
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> dict[str, list[float]]:
        names = [self._tool_name(t) for t in tools]
        phrases = [
            f"{name}: {t.get('function', {}).get('description', '')}".strip(": ")
            for name, t in zip(names, tools)
        ]
        if hasattr(client, "embed_documents_tracked"):
            local_usage: dict[str, Any] = {}
            vectors = await client.embed_documents_tracked(phrases, usage_sink=local_usage)
            from ai_services.providers.usage_reporting import accumulate_usage_sink
            accumulate_usage_sink(usage_sink, local_usage)
        else:
            vectors = await client.embed_documents(phrases)
        return dict(zip(names, vectors))

    def _warn_once(self, msg: str) -> None:
        if not MCPToolSelector._warned_no_provider:
            MCPToolSelector._warned_no_provider = True
            logger.warning("MCP tool selection falling back to full tool list: %s", msg)
