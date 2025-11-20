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
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Return a minimal payload preserving any metadata provided."""
        self.logger.debug("format_document called on conversational adapter; returning metadata only")
        return {
            "content": raw_doc or "",
            "metadata": metadata.copy() if metadata else {},
        }

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Passthrough adapters never extract direct answers."""
        return None

    def apply_domain_specific_filtering(
        self,
        context_items: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """Return the context items unchanged for passthrough usage."""
        return context_items


class MultimodalAdapter(DocumentAdapter):
    """Domain adapter for multimodal conversational interactions with file context."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        super().__init__(config=config or {}, **kwargs)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document with file chunk metadata.
        
        Preserves file metadata (file_id, chunk_index, filename) for context.
        """
        self.logger.debug("format_document called on multimodal adapter; preserving file metadata")
        return {
            "content": raw_doc or "",
            "metadata": metadata.copy() if metadata else {},
        }

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Multimodal adapters never extract direct answers."""
        return None

    def apply_domain_specific_filtering(
        self,
        context_items: List[Dict[str, Any]],
        query: str,
    ) -> List[Dict[str, Any]]:
        """
        Return the context items unchanged.
        
        File chunks from vector store are already filtered by similarity,
        so no additional filtering is needed here.
        """
        return context_items


__all__ = ["ConversationalAdapter", "MultimodalAdapter"]
