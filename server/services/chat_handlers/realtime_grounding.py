"""
Provider-agnostic grounding for real-time speech-to-speech voice adapters.

A realtime adapter (e.g. type: "openai_realtime") can point at an existing
retriever adapter via config.grounding_adapter to answer factual questions
with live RAG lookups instead of a static baked-in prompt. This module is
kept independent of any specific realtime provider's wire protocol (OpenAI,
future Gemini/Mistral/local) — only the tool-schema shape and the retrieval
call itself live here; each provider's websocket handler translates
build_tool_schema()'s neutral dict into its own session/tool format and maps
its own function-call events to execute_grounding_lookup().
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class GroundingConfig:
    adapter_name: str
    tool_name: str
    tool_description: str
    confidence_threshold: Optional[float] = None
    max_answer_chars: int = 600


def resolve_grounding_config(adapter_config: Dict[str, Any]) -> Optional[GroundingConfig]:
    """Build a GroundingConfig from adapter YAML config, or None if ungrounded."""
    cfg = adapter_config.get("config") or {}
    grounding_adapter = cfg.get("grounding_adapter")
    if not grounding_adapter:
        return None
    return GroundingConfig(
        adapter_name=grounding_adapter,
        tool_name=cfg.get("grounding_tool_name", "lookup_answer"),
        tool_description=cfg.get(
            "grounding_tool_description",
            "Look up a factual answer from the knowledge base for the user's question.",
        ),
        confidence_threshold=cfg.get("grounding_confidence_threshold"),
        max_answer_chars=int(cfg.get("grounding_max_answer_chars", 600)),
    )


def build_tool_schema(grounding: GroundingConfig) -> Dict[str, Any]:
    """Neutral JSON-schema function-calling tool definition.

    OpenAI Realtime's session.tools accepts this shape directly; a future
    provider's handler would translate this same dict into its own format.
    """
    return {
        "type": "function",
        "name": grounding.tool_name,
        "description": grounding.tool_description,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's question, in their own words.",
                }
            },
            "required": ["query"],
        },
    }


async def execute_grounding_lookup(
    adapter_manager: Any,
    grounding: GroundingConfig,
    query: str,
    api_key: Optional[str] = None,
) -> str:
    """Run the grounding retriever and return a short, speakable text answer."""
    if not adapter_manager:
        logger.warning("Grounding lookup requested but no adapter_manager is available")
        return "I don't have access to that information right now."

    try:
        adapter = await adapter_manager.get_adapter(grounding.adapter_name)
        kwargs: Dict[str, Any] = {}
        if grounding.confidence_threshold is not None:
            kwargs["confidence_threshold"] = grounding.confidence_threshold
        docs = await adapter.get_relevant_context(query=query, api_key=api_key, **kwargs)
    except Exception as e:
        logger.error(
            "Grounding lookup failed for adapter '%s': %s", grounding.adapter_name, e, exc_info=True
        )
        return "I couldn't find an answer to that just now."

    if not docs:
        return "I don't have information about that."

    return _format_answer(docs, grounding.max_answer_chars)


def _format_answer(docs: list, max_chars: int) -> str:
    """Join the top retrieved answers into a short plain-text block.

    Voice answers are spoken aloud, so this favors terse "answer" text over
    the markdown/toon table formatting used for LLM prompt injection.
    """
    parts = []
    total = 0
    for doc in docs:
        text = doc.get("answer") or doc.get("content") or ""
        text = " ".join(text.split())
        if not text:
            continue
        # Account for the joining space that precedes every part after the first,
        # so the final " ".join(parts) never exceeds max_chars.
        sep = 1 if parts else 0
        remaining = max_chars - total - sep
        if remaining <= 0:
            break
        if len(text) > remaining:
            parts.append(text[:remaining].rstrip())
            break
        parts.append(text)
        total += len(text) + sep
    return " ".join(parts) if parts else "I don't have information about that."
