"""Shared utilities for pipeline steps."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from utils.generation_memory import generation_memory_key

logger = logging.getLogger(__name__)

# Adapter types that never call the main inference LLM — each has its own
# dedicated pipeline step (or, for 'fetch'/'openai_realtime'/'gemini_live', bypasses it entirely).
NO_LLM_ADAPTER_TYPES = frozenset({
    'image_generation',
    'video_generation',
    'document_generation',
    'audio_generation',
    'mcp_agent',
    'fetch',
    'openai_realtime',
    'openai_realtime_translation',
    'gemini_live',
})

# Adapter types that have no use for an inference_provider/rewrite_provider at all —
# unlike image/video/document generation (which still resolve an LLM via rewrite_provider),
# these never call any text-inference provider, so preload/validation should skip them
# entirely rather than falling back to the global default provider.
NO_INFERENCE_PROVIDER_ADAPTER_TYPES = frozenset({
    'fetch',
    'openai_realtime',
    'openai_realtime_translation',
    'gemini_live',
})


def get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


def get_rewrite_prompt_config(container, kind: str) -> Dict[str, Any]:
    """Return the externalized rewrite-prompt config for a generation kind.

    Loaded once at server startup from config/rewriters-prompts.yaml (imported by
    config.yaml) and cached for the process lifetime as part of the main config
    dict — same caching model as every other imported config file (tts.yaml,
    image.yaml, etc.). `kind` is one of: 'image', 'video', 'audio', 'document'.
    """
    config = container.get_or_none('config') or {}
    return config.get('rewriters', {}).get(kind, {}) or {}


async def get_generation_memory(container, adapter_name: str, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the last stored generation memory (effective prompt/spec) for this
    adapter+session, so a follow-up like "add another dog" can be merged with
    what was actually generated last turn instead of re-running the rewrite LLM
    on the raw message alone.

    Reuses ThreadDatasetService (see conversation_threading config) as a generic
    session-scoped KV cache — independent of the client-driven /threads flow that
    intent-SQL retrieval uses, since generation follow-ups shouldn't require an
    extra round trip to opt in.
    """
    if not session_id or not adapter_name or not container.has('thread_dataset_service'):
        return None
    dataset_service = container.get('thread_dataset_service')
    if not dataset_service or not getattr(dataset_service, 'enabled', False):
        return None
    try:
        # store_dataset() transforms thread_id -> dataset_key internally (cache-key
        # prefixing / db-key formatting) before storing; get_dataset() expects that
        # already-transformed key, so recompute the same deterministic transform here.
        dataset_key = dataset_service._generate_dataset_key(generation_memory_key(adapter_name, session_id))
        result = await dataset_service.get_dataset(dataset_key)
        return result[0] if result else None
    except Exception as e:
        logger.debug("Could not fetch generation memory for '%s': %s", adapter_name, e)
        return None


def record_usage(
    container,
    context,
    usage_sink: Dict[str, Any],
    provider: Optional[str],
    model: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Turn a raw usage_sink (filled by generate_tracked/generate_stream_tracked/
    generate_with_tools_tracked, possibly summed via accumulate_usage_sink)
    into context.metadata["usage"], adding a cost estimate from the pricing
    service when available. Never raises — usage/cost is best-effort.

    Shared by LLMInferenceStep (plain generation and the inline MCP-tools
    branch) and MCPAgentStep (explicit skill-swap tool loop), so both surfaces
    price usage identically instead of duplicating the pricing-service lookup.

    extra: additional keys merged into the usage dict as-is (e.g. `calls`,
    `source`) — set AFTER pricing so callers can't accidentally clobber the
    priced fields.
    """
    reported = bool(usage_sink.get("reported"))
    prompt_tokens = usage_sink.get("prompt_tokens") if reported else None
    completion_tokens = usage_sink.get("completion_tokens") if reported else None
    total_tokens = usage_sink.get("total_tokens") if reported else None
    # Informational only — the subset of completion_tokens spent on
    # reasoning/thinking, when the provider breaks it out (OpenAI
    # o-series/gpt-5, Gemini). Already folded into completion_tokens
    # above, so this never changes the cost estimate below.
    reasoning_tokens = usage_sink.get("reasoning_tokens") if reported else None

    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "provider": provider,
        "model": model,
        "cost_usd": None,
        "input_rate_per_1m": None,
        "output_rate_per_1m": None,
        "pricing_source": "unreported" if not reported else "unpriced",
        "reported": reported,
    }

    if reported and container.has('pricing_service'):
        try:
            pricing_service = container.get('pricing_service')
            estimate = pricing_service.estimate(provider, model, prompt_tokens, completion_tokens)
            usage["cost_usd"] = estimate.cost_usd
            usage["input_rate_per_1m"] = estimate.input_rate_per_1m
            usage["output_rate_per_1m"] = estimate.output_rate_per_1m
            usage["pricing_source"] = estimate.pricing_source
        except Exception:
            logger.debug("Pricing estimate failed", exc_info=True)

    if extra:
        usage.update(extra)

    # Mirror token counts at the metadata top level so
    # OpenAIResponseFormatter.build_usage (which reads metadata directly)
    # also reports real numbers on the /v1/chat/completions surface.
    context.metadata["usage"] = usage
    if reported:
        context.metadata["prompt_tokens"] = prompt_tokens
        context.metadata["completion_tokens"] = completion_tokens
        context.metadata["total_tokens"] = total_tokens


def record_media_generation_usage(
    container,
    context,
    provider: Optional[str],
    model: Optional[str],
    token_usage: Optional[Dict[str, Any]] = None,
    media_usage: Optional[Dict[str, Any]] = None,
    rewrite_sink: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record usage/cost for an image/video/audio-generation pipeline step,
    combining the generation call's own usage with the (separate) rewrite
    LLM call that turned the user's message into a generation prompt — both
    are real spend for the same request and belong on one audit row.

    Exactly one of token_usage (gpt-image-1/gemini-image style, tokens) or
    media_usage ({"unit", "quantity"}, everything billed per unit) should be
    passed, matching what the generation service actually returned. Never
    raises — usage/cost is best-effort.

    Simplification: the two cost components (generation, rewrite) are priced
    independently against their own provider/model and summed; a missing/
    unpriced component contributes $0 to the total rather than blocking the
    other, consistent with cost already being labeled an estimate everywhere
    in the UI. `pricing_source` reflects the generation call, since that's
    the dominant, request-defining cost.
    """
    pricing_service = container.get('pricing_service') if container.has('pricing_service') else None

    usage: Dict[str, Any] = {
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
        "reasoning_tokens": None, "provider": provider, "model": model,
        "cost_usd": None, "input_rate_per_1m": None, "output_rate_per_1m": None,
        "pricing_source": "unreported", "usage_unit": None, "usage_quantity": None,
        "reported": False,
    }
    total_cost = 0.0
    have_cost = False

    if token_usage and token_usage.get("reported"):
        prompt_tokens = token_usage.get("prompt_tokens") or 0
        completion_tokens = token_usage.get("completion_tokens") or 0
        usage.update({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "reported": True,
        })
        if pricing_service:
            try:
                estimate = pricing_service.estimate(provider, model, prompt_tokens, completion_tokens)
                usage["input_rate_per_1m"] = estimate.input_rate_per_1m
                usage["output_rate_per_1m"] = estimate.output_rate_per_1m
                usage["pricing_source"] = estimate.pricing_source
                if estimate.cost_usd is not None:
                    total_cost += estimate.cost_usd
                    have_cost = True
            except Exception:
                logger.debug("Pricing estimate failed for media generation", exc_info=True)
    elif media_usage:
        usage.update({
            "usage_unit": media_usage.get("unit"),
            "usage_quantity": media_usage.get("quantity"),
            "reported": True,
        })
        if pricing_service:
            try:
                estimate = pricing_service.estimate_media(
                    provider, model, media_usage.get("unit"), media_usage.get("quantity"),
                )
                usage["pricing_source"] = estimate.pricing_source
                if estimate.cost_usd is not None:
                    total_cost += estimate.cost_usd
                    have_cost = True
            except Exception:
                logger.debug("Media pricing estimate failed for media generation", exc_info=True)

    if rewrite_sink and rewrite_sink.get("reported"):
        rewrite_provider = rewrite_sink.get("provider")
        rewrite_model = rewrite_sink.get("model")
        rewrite_prompt_tokens = rewrite_sink.get("prompt_tokens") or 0
        rewrite_completion_tokens = rewrite_sink.get("completion_tokens") or 0
        usage["rewrite_prompt_tokens"] = rewrite_prompt_tokens
        usage["rewrite_completion_tokens"] = rewrite_completion_tokens
        usage["rewrite_provider"] = rewrite_provider
        usage["rewrite_model"] = rewrite_model
        if pricing_service:
            try:
                rewrite_estimate = pricing_service.estimate(
                    rewrite_provider, rewrite_model, rewrite_prompt_tokens, rewrite_completion_tokens,
                )
                if rewrite_estimate.cost_usd is not None:
                    total_cost += rewrite_estimate.cost_usd
                    have_cost = True
            except Exception:
                logger.debug("Pricing estimate failed for rewrite LLM call", exc_info=True)

    if have_cost:
        usage["cost_usd"] = round(total_cost, 6)

    context.metadata["usage"] = usage
    if usage["reported"] and usage["total_tokens"] is not None:
        context.metadata["prompt_tokens"] = usage["prompt_tokens"]
        context.metadata["completion_tokens"] = usage["completion_tokens"]
        context.metadata["total_tokens"] = usage["total_tokens"]


async def store_generation_memory(
    container, adapter_name: str, session_id: Optional[str], memory: Dict[str, Any]
) -> None:
    """Store this turn's effective generation prompt/spec for future follow-ups."""
    if not session_id or not adapter_name or not container.has('thread_dataset_service'):
        return
    dataset_service = container.get('thread_dataset_service')
    if not dataset_service or not getattr(dataset_service, 'enabled', False):
        return
    try:
        await dataset_service.store_dataset(
            thread_id=generation_memory_key(adapter_name, session_id),
            query_context=memory,
            raw_results=[],
        )
    except Exception as e:
        logger.debug("Could not store generation memory for '%s': %s", adapter_name, e)
