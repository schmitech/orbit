"""
Usage Reporting Mixin
=====================

Opt-in capability for inference service implementations to report token
usage back to the caller via a per-call mutable ``usage_sink`` dict, without
changing the ``generate()``/``generate_stream() -> str`` contract and
without risking cross-request state on shared/cached service instances.

A class only receives a ``usage_sink`` kwarg if it mixes this in AND sets
``SUPPORTS_USAGE_REPORTING = True`` — most implementations pass ``**kwargs``
straight into the provider SDK call, so an un-migrated implementation must
never see this kwarg.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class UsageReportingMixin:
    """Mixed into inference services that can report token usage."""

    SUPPORTS_USAGE_REPORTING = True

    @staticmethod
    def _take_usage_sink(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Pop the usage_sink kwarg. Must be the first line of a migrated generate()."""
        return kwargs.pop("usage_sink", None)

    @staticmethod
    def _extract_reasoning_tokens(usage: Any) -> Optional[int]:
        """
        Reasoning-token sub-count, for providers using an OpenAI-shaped usage
        object. Chat Completions nests it under completion_tokens_details,
        the Responses API (web search) under output_tokens_details — same
        field name, different parent. Purely informational; already
        included in the parent completion/output token total used for
        cost, so a miss here (an unset attribute, or a provider that simply
        doesn't populate it) just means "not reported," never a cost error.
        """
        if usage is None:
            return None
        details = getattr(usage, "completion_tokens_details", None) or getattr(usage, "output_tokens_details", None)
        return getattr(details, "reasoning_tokens", None) if details is not None else None

    @staticmethod
    def _usage_value(value: Any, key: str) -> Any:
        """Read one usage field from either an SDK object or a JSON dict."""
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None) if value is not None else None

    @classmethod
    def _embedding_prompt_tokens(cls, usage: Any) -> Optional[int]:
        """Return the input-only token count from an embedding usage object."""
        prompt_tokens = cls._usage_value(usage, "prompt_tokens")
        if prompt_tokens is not None:
            return prompt_tokens
        input_tokens = cls._usage_value(usage, "input_tokens")
        if input_tokens is not None:
            return input_tokens
        return cls._usage_value(usage, "total_tokens")

    def _report_usage(
        self,
        sink: Optional[Dict[str, Any]],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        reasoning_tokens: Optional[int] = None,
    ) -> None:
        """
        Fill the caller-supplied sink dict with usage for this call.

        reasoning_tokens is the subset of completion_tokens spent on
        reasoning/thinking (e.g. OpenAI o-series/gpt-5
        completion_tokens_details.reasoning_tokens, Gemini
        thoughts_token_count) — purely informational, already folded into
        completion_tokens for cost purposes. None when the provider doesn't
        report it separately.
        """
        if sink is None:
            return
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        sink.update({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "model": getattr(self, "model", None),
            "provider": getattr(self, "provider_name", None),
            "reported": True,
        })

    def _report_media_usage(
        self,
        sink: Optional[Dict[str, Any]],
        unit: str,
        quantity: Optional[float],
    ) -> None:
        """
        Fill the caller-supplied sink with a discrete-unit media usage report
        (images, video seconds, TTS characters, STT seconds, OCR pages) — the
        media counterpart of _report_usage() above, for services billed per
        unit rather than per token. Only reports when quantity is known; never
        guesses a quantity from unrelated data (e.g. byte length).
        """
        if sink is None or quantity is None:
            return
        sink.update({
            "usage_unit": unit,
            "usage_quantity": quantity,
            "model": getattr(self, "model", None),
            "provider": getattr(self, "provider_name", None),
            "reported": True,
        })


def accumulate_usage_sink(
    target: Optional[Dict[str, Any]],
    source: Optional[Dict[str, Any]],
) -> None:
    """
    Sum a per-call usage_sink into a caller-owned accumulator, for callers
    (like the MCP tool-calling loop) that make multiple provider calls.

    _report_usage() above overwrites its sink on every call, so it is never
    safe to pass one shared sink across multiple provider calls — each call
    needs its own fresh sink, summed here. Token counts are additive; model/
    provider are taken from the first reporting call (they don't change
    mid-loop); reported/calls track whether *any* call actually reported so
    a partial loop (some calls reported, some didn't) is still visible.
    """
    if target is None or not source or not source.get("reported"):
        return

    target["calls"] = target.get("calls", 0) + 1
    target["reported"] = True
    target.setdefault("provider", source.get("provider"))
    target.setdefault("model", source.get("model"))

    # Preserve independently priceable calls as line items. This matters when
    # one request uses more than one provider/model (for example skill-routing
    # and RAG embeddings before the final inference call): token totals are
    # additive, but each call must be priced against its own rate.
    source_items = source.get("line_items")
    if source_items:
        target.setdefault("line_items", []).extend(dict(item) for item in source_items)
    else:
        target.setdefault("line_items", []).append({
            "provider": source.get("provider"),
            "model": source.get("model"),
            "prompt_tokens": source.get("prompt_tokens") or 0,
            "completion_tokens": source.get("completion_tokens") or 0,
            "total_tokens": source.get("total_tokens") or 0,
            "reasoning_tokens": source.get("reasoning_tokens"),
            "usage_unit": source.get("usage_unit"),
            "usage_quantity": source.get("usage_quantity"),
            "reported": True,
        })

    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        target[key] = (target.get(key) or 0) + (source.get(key) or 0)

    source_reasoning = source.get("reasoning_tokens")
    if source_reasoning is not None:
        target["reasoning_tokens"] = (target.get("reasoning_tokens") or 0) + source_reasoning
