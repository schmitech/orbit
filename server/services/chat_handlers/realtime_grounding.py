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
    max_rows: int = 3


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
        max_rows=max(1, int(cfg.get("grounding_max_rows", 3))),
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

    return _format_answer(docs, grounding.max_answer_chars, grounding.max_rows)


def _format_answer(docs: list, max_chars: int, max_rows: int = 3) -> str:
    """Return bounded, speech-friendly retrieval content.

    QA retrievers provide a ready-to-speak ``answer``. Intent retrievers also
    expose their pre-rendered table as structured ``metadata.formatted_data``;
    use that structure instead of slicing markdown, CSV, or TOON text midway
    through a row. The realtime model can then turn the concise facts into a
    natural response.
    """
    parts = []
    total = 0
    for doc in docs:
        structured_table = _has_structured_table(doc)
        for text in _document_segments(doc, max_rows):
            text = _normalize_text(text)
            if not text:
                continue

            # Account for the joining space so the final output is always
            # within the configured character budget.
            remaining = max_chars - total - (1 if parts else 0)
            if remaining <= 0:
                return " ".join(parts) if parts else "I don't have information about that."
            if len(text) > remaining:
                # Intent rows are discrete facts. Do not turn the next row
                # into a fragment merely because the character cap is near.
                if structured_table:
                    return " ".join(parts) if parts else "I don't have information about that."
                clipped = _truncate_at_word_boundary(text, remaining)
                if clipped:
                    parts.append(clipped)
                return " ".join(parts) if parts else "I don't have information about that."

            parts.append(text)
            total += len(text) + (1 if len(parts) > 1 else 0)

    return " ".join(parts) if parts else "I don't have information about that."


def _has_structured_table(doc: Dict[str, Any]) -> bool:
    metadata = doc.get("metadata")
    formatted = metadata.get("formatted_data") if isinstance(metadata, dict) else None
    return isinstance(formatted, dict) and isinstance(formatted.get("table"), dict)


def _document_segments(doc: Dict[str, Any], max_rows: int) -> list[str]:
    """Extract voice-safe segments from one retriever result."""
    answer = doc.get("answer")
    if answer:
        return [str(answer)]

    metadata = doc.get("metadata")
    formatted = metadata.get("formatted_data") if isinstance(metadata, dict) else None
    if isinstance(formatted, dict):
        summary = formatted.get("summary")
        if summary:
            return [str(summary)]

        table = formatted.get("table")
        if isinstance(table, dict) and isinstance(table.get("rows"), list):
            rows = table["rows"]
            columns = table.get("columns") or []
            segments = []
            message = formatted.get("message")
            if message:
                segments.append(str(message))
            elif formatted.get("result_count") is not None:
                segments.append(f"Found {formatted['result_count']} results.")

            for row in rows[:max_rows]:
                values = row.values() if isinstance(row, dict) else row
                if not isinstance(values, (list, tuple)):
                    values = [values]
                fields = []
                for index, value in enumerate(values):
                    if value in (None, ""):
                        continue
                    label = columns[index] if index < len(columns) else f"Field {index + 1}"
                    fields.append(f"{label}: {value}")
                if fields:
                    segments.append("; ".join(fields))
            if segments:
                return segments

        message = formatted.get("message")
        if message:
            return [str(message)]

    content = doc.get("content") or ""
    # Keep line boundaries for unstructured tabular content. This avoids
    # emitting a partial table row when a non-intent retriever returns text.
    return [line for line in str(content).splitlines() if line.strip()]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value).split())


def _truncate_at_word_boundary(text: str, max_chars: int) -> str:
    """Truncate prose without splitting a word; callers already cap rows."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rstrip()
    boundary = clipped.rfind(" ")
    return clipped[:boundary].rstrip() if boundary > 0 else clipped
