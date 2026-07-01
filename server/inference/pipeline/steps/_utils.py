"""Shared utilities for pipeline steps."""
from __future__ import annotations

from typing import Optional

# Adapter types that never call the main inference LLM — each has its own
# dedicated pipeline step (or, for 'fetch'/'openai_realtime', bypasses it entirely).
NO_LLM_ADAPTER_TYPES = frozenset({
    'image_generation',
    'video_generation',
    'document_generation',
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
