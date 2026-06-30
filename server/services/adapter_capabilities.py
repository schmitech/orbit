"""Helpers for interpreting adapter capability configuration."""

from typing import Any, Dict


def uses_retrieval_services(adapter_config: Dict[str, Any]) -> bool:
    capabilities = adapter_config.get('capabilities') or {}

    retrieval_behavior = capabilities.get('retrieval_behavior')
    if retrieval_behavior is not None:
        return str(retrieval_behavior).lower() != 'none'

    if capabilities.get('retrieval') or capabilities.get('semantic_search'):
        return True

    # Adapters that declare type: but no explicit capabilities block: treat all
    # non-passthrough types as retrieval-enabled.
    return adapter_config.get('type') != 'passthrough'
