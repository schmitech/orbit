"""Follow-up query rewriting for intent retrievers (SQL/HTTP).

Not a PipelineStep of its own — invoked inline from context_retrieval.py, right
before the intent retriever is called, only for adapters with the
`supports_followup_rewrite` capability. Turns a follow-up like "what about
Ottawa" into a standalone question ("How many customers bought in Ottawa")
using the previous turn's resolved query/parameters, stashed by the retriever
in services/intent_followup_state.py. See docs/sql-retriever-architecture.md
and the approved plan for the design rationale.

Cost note: once a last-turn entry exists for a session, every subsequent turn
within the TTL window calls this rewrite LLM — including turns that are not
actually follow-ups — since deciding that is exactly what the LLM call is for.
This is an accepted cost of the first version; use a small/cheap
`rewrite_model` on the adapter to keep it inexpensive.
"""

import asyncio
import logging
from typing import Any

from services.intent_followup_state import get_last_turn

from ._utils import get_rewrite_prompt_config

logger = logging.getLogger(__name__)

_REWRITE_TIMEOUT_SECONDS = 5.0
_MAX_REWRITTEN_LENGTH = 500


async def _resolve_rewrite_provider(container, adapter_name: str):
    """Resolve the LLM provider for the intent follow-up rewrite call.

    Priority: adapter's own `rewrite_provider`/`rewrite_model` -> adapter's
    `inference_provider` -> global `llm_provider` fallback. Mirrors
    AudioGenerationStep._resolve_rewrite_provider (inference/pipeline/steps/audio_generation.py).
    """
    if container.has('adapter_manager'):
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            rewrite_provider_name = adapter_config.get('rewrite_provider')
            rewrite_model = adapter_config.get('rewrite_model') or None
            if rewrite_provider_name:
                try:
                    provider = await adapter_manager.get_overridden_provider(
                        rewrite_provider_name, adapter_name,
                        explicit_model_override=rewrite_model,
                    )
                    if provider:
                        logger.debug(
                            "Using rewrite_provider '%s' (model=%r) for intent follow-up rewrite",
                            rewrite_provider_name, rewrite_model,
                        )
                        return provider
                except Exception as e:  # noqa: BLE001 - rewrite provider resolution is best-effort, falls back to default
                    logger.debug("Could not resolve rewrite_provider '%s': %s", rewrite_provider_name, e)

            inference_provider = adapter_config.get('inference_provider')
            if inference_provider:
                try:
                    provider = await adapter_manager.get_overridden_provider(inference_provider, adapter_name)
                    if provider:
                        logger.debug(
                            "Using inference provider '%s' for intent follow-up rewrite", inference_provider,
                        )
                        return provider
                except Exception as e:  # noqa: BLE001 - rewrite provider resolution is best-effort, falls back to default
                    logger.debug("Could not resolve provider for '%s': %s", adapter_name, e)

    return container.get_or_none('llm_provider')


def _format_previous_parameters(parameters: dict[str, Any] | None) -> str:
    if not parameters:
        return "none"
    parts = [f"{k}={v}" for k, v in parameters.items() if v is not None]
    return ", ".join(parts) if parts else "none"


def _is_valid_rewrite(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_REWRITTEN_LENGTH:
        return False
    return "\n" not in text


async def maybe_rewrite_followup_query(
    container, adapter_name: str, session_id: str | None, message: str,
    usage_sink: dict[str, Any] | None = None,
    state_key: str | None = None,
) -> str:
    """Return the query to send to the intent retriever's template matching:
    `message` rewritten into a standalone question if it's a follow-up to the
    previous turn on this (adapter, session), or `message` unchanged otherwise
    (including on any failure — this must never block or corrupt the turn).

    `adapter_name` is the configured adapter name, used to resolve the rewrite
    LLM provider. `state_key` is the key the retriever actually stored its last
    turn under (its `audit_adapter_name` or class name — see
    `_clarification_adapter_key()`/`_store_followup_turn()` in intent_sql_base.py
    /intent_http_base.py) — it must match that key exactly, since the two can
    differ (e.g. the static-retriever fallback path leaves `audit_adapter_name`
    unset). Defaults to `adapter_name` when not given.
    """
    if not session_id:
        return message

    last_turn = get_last_turn(state_key or adapter_name, session_id)
    if not last_turn:
        return message

    llm_provider = await _resolve_rewrite_provider(container, adapter_name)
    if not llm_provider:
        logger.debug("No llm_provider available for intent follow-up rewrite — using raw message")
        return message

    prompt_cfg = get_rewrite_prompt_config(container, 'intent_query')
    template = prompt_cfg.get('template')
    if not template:
        logger.warning("No 'intent_query' rewrite template in config/rewriters-prompts.yaml — using raw message")
        return message
    max_tokens = prompt_cfg.get('max_tokens', 150)
    temperature = prompt_cfg.get('temperature', 0.1)

    try:
        rewrite_prompt = template.format(
            previous_query=last_turn.get("effective_query", ""),
            previous_parameters=_format_previous_parameters(last_turn.get("parameters")),
            message=message,
        )
    except (KeyError, IndexError) as e:
        logger.warning(f"Malformed 'intent_query' rewrite template in config/rewriters-prompts.yaml: {e}")
        return message

    try:
        rewritten = await asyncio.wait_for(
            llm_provider.generate_tracked(
                rewrite_prompt, usage_sink=usage_sink, max_tokens=max_tokens, temperature=temperature,
            ),
            timeout=_REWRITE_TIMEOUT_SECONDS,
        )
        rewritten = (rewritten or "").strip()
        for quote in ('"', "'"):
            if rewritten.startswith(quote) and rewritten.endswith(quote) and len(rewritten) > 2:
                rewritten = rewritten[1:-1].strip()
                break
        if _is_valid_rewrite(rewritten):
            logger.debug("Rewrote follow-up query: %r -> %r", message[:80], rewritten[:80])
            return rewritten
        logger.debug("Intent follow-up rewrite returned empty/malformed output — using raw message")
    except TimeoutError:
        logger.warning("Intent follow-up rewrite timed out — using raw message")
    except Exception as e:  # noqa: BLE001 - rewrite is best-effort; falls back to raw message
        logger.warning(f"Failed to rewrite follow-up query: {e}")

    return message
