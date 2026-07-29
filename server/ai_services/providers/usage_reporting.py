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
