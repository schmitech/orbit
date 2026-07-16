"""Shared utilities for pipeline steps."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from utils.generation_memory import generation_memory_key

logger = logging.getLogger(__name__)

# Adapter types that never call the main inference LLM — each has its own
# dedicated pipeline step (or, for 'fetch'/'openai_realtime', bypasses it entirely).
NO_LLM_ADAPTER_TYPES = frozenset({
    'image_generation',
    'video_generation',
    'document_generation',
    'audio_generation',
    'mcp_agent',
    'fetch',
    'openai_realtime',
})

# Adapter types that have no use for an inference_provider/rewrite_provider at all —
# unlike image/video/document generation (which still resolve an LLM via rewrite_provider),
# these never call any text-inference provider, so preload/validation should skip them
# entirely rather than falling back to the global default provider.
NO_INFERENCE_PROVIDER_ADAPTER_TYPES = frozenset({
    'fetch',
    'openai_realtime',
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
