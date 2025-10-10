"""
Base adapter classes for document transformation and domain-specific formatting.

This module defines the core interfaces and base classes for all adapters in the system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import logging

# Configure logging
logger = logging.getLogger(__name__)


class DocumentAdapter(ABC):
    """
    Abstract base class for adapting documents to specific domain representations.

    This interface allows extending retrievers to different domains without changing
    core retrieval logic. Each domain adapter is responsible for:
    - Formatting raw documents into domain-specific structures
    - Extracting direct answers when applicable
    - Applying domain-specific filtering and ranking
    """

    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize the document adapter.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        self.config = config or {}

    @abstractmethod
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format raw document and metadata for a specific domain.

        Args:
            raw_doc: The raw document content
            metadata: Document metadata

        Returns:
            A formatted document representation suitable for the domain
        """
        pass

    @abstractmethod
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context items if applicable to this domain.

        Args:
            context: List of context items

        Returns:
            A direct answer if found, otherwise None
        """
        pass

    @abstractmethod
    def apply_domain_specific_filtering(self,
                                       context_items: List[Dict[str, Any]],
                                       query: str) -> List[Dict[str, Any]]:
        """
        Apply domain-specific filtering or ranking to context items.

        Args:
            context_items: Context items from vector search or retrieval
            query: The user's query

        Returns:
            Filtered and/or reranked context items
        """
        pass
