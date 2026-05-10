"""Conversational passthrough document adapter."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from adapters.base import DocumentAdapter

logger = logging.getLogger(__name__)


class ConversationalAdapter(DocumentAdapter):
    """Domain adapter for conversational passthrough interactions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        super().__init__(config=config or {}, **kwargs)

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": raw_doc or "",
            "metadata": metadata.copy() if metadata else {},
        }

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        return None

    def apply_domain_specific_filtering(
        self,
        context_items: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        return context_items


class MultimodalAdapter(ConversationalAdapter):
    """Domain adapter for multimodal conversational interactions with file context.

    File chunks from vector store are already filtered by similarity, so no
    additional filtering or answer extraction is needed beyond the passthrough behaviour.
    """


__all__ = ["ConversationalAdapter", "MultimodalAdapter"]
