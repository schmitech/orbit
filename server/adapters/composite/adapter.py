"""
Composite Adapter for multi-source intent routing.

This adapter is a minimal implementation used by the CompositeIntentRetriever.
The actual domain-specific logic is handled by the child adapters that the
composite retriever routes to.
"""

import logging
from typing import Dict, Any, List, Optional

from adapters.base import DocumentAdapter
from adapters.registry import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)


class CompositeAdapter(DocumentAdapter):
    """
    Minimal domain adapter for composite intent retrievers.

    The CompositeIntentRetriever routes queries to child adapters, each with
    their own domain adapters. This adapter provides the required interface
    but delegates actual work to the child adapters.
    """

    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize the composite adapter.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        super().__init__(config=config, **kwargs)
        self.confidence_threshold = kwargs.get('confidence_threshold', 0.4)
        logger.debug("CompositeAdapter initialized")

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document - passthrough since child adapters handle formatting.

        Args:
            raw_doc: The raw document content
            metadata: Document metadata

        Returns:
            Basic formatted document
        """
        return {
            "content": raw_doc,
            "metadata": metadata,
            "confidence": metadata.get('confidence', 1.0)
        }

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract direct answer - delegates to child adapter results.

        Args:
            context: List of context items (already processed by child adapter)

        Returns:
            Direct answer if found in context
        """
        # Child adapters have already processed the context
        # Check if any item has a direct answer
        for item in context:
            if isinstance(item, dict):
                direct = item.get('direct_answer')
                if direct:
                    return direct
        return None

    def apply_domain_specific_filtering(
        self,
        context_items: List[Dict[str, Any]],
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Apply filtering - passthrough since child adapters handle filtering.

        Args:
            context_items: Context items from child adapter
            query: The user's query

        Returns:
            Context items unchanged (already filtered by child adapter)
        """
        # Child adapters have already applied their domain-specific filtering
        return context_items


def register_composite_adapter():
    """Register composite adapter with the global adapter registry."""
    logger.info("Registering composite adapter with global registry...")

    try:
        # Register for 'none' datasource since composite doesn't use a specific datasource
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource="none",
            adapter_name="composite",
            implementation='adapters.composite.adapter.CompositeAdapter',
            config={
                'confidence_threshold': 0.4
            }
        )
        logger.info("Registered composite adapter for datasource=none")

    except Exception as e:
        logger.error(f"Failed to register composite adapter: {e}")


# Register when module is imported
register_composite_adapter()
