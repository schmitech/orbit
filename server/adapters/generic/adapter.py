"""
Generic document adapter for general-purpose document retrieval.

This adapter provides basic document formatting and filtering without
domain-specific logic (unlike QA or Intent adapters).
"""

from typing import Dict, Any, List, Optional
import logging
from adapters.base import DocumentAdapter

# Configure logging
logger = logging.getLogger(__name__)


class GenericDocumentAdapter(DocumentAdapter):
    """Adapter for generic document retrieval (not QA-specific)"""

    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize generic document adapter.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        super().__init__(config=config, **kwargs)

        # Extract configuration values with sensible defaults
        self.confidence_threshold = self.config.get('confidence_threshold', 0.3)

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for general retrieval"""
        item = {
            "raw_document": raw_doc,
            "content": raw_doc,
            "metadata": metadata.copy() if metadata else {},
        }

        # Extract title if available
        if metadata and "title" in metadata:
            item["title"] = metadata["title"]

        return item

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Generic documents don't have direct answers"""
        return None

    def apply_domain_specific_filtering(self,
                                      context_items: List[Dict[str, Any]],
                                      query: str) -> List[Dict[str, Any]]:
        """Apply generic content filtering"""
        if not context_items:
            return []

        # Filter out items below confidence threshold
        filtered_items = [item for item in context_items
                         if item.get("confidence", 0) >= self.confidence_threshold]

        # Sort by confidence score
        filtered_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        return filtered_items
