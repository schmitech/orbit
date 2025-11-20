"""
Base QA (Question-Answer) adapter for document retrieval.

This module provides the base adapter for QA-specific document formatting,
answer extraction, and filtering logic.
"""

from typing import Dict, Any, List, Optional
import logging
from adapters.base import DocumentAdapter

# Configure logging
logger = logging.getLogger(__name__)


class QADocumentAdapter(DocumentAdapter):
    """Adapter for question-answer type documents"""

    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize QA document adapter.

        Args:
            config: Optional configuration dictionary
            **kwargs: Additional parameters
        """
        super().__init__(config=config, **kwargs)

        # Extract configuration values with sensible defaults
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.boost_exact_matches = self.config.get('boost_exact_matches', False)

        logger.debug(f"Initialized QA Document Adapter with confidence threshold: {self.confidence_threshold}")

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for QA domain"""
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy() if metadata else {},
        }

        if metadata and "question" in metadata and "answer" in metadata:
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
        else:
            item["content"] = raw_doc

        return item

    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Extract a direct answer from QA pairs"""
        if not context:
            return None

        first_result = context[0]

        if ("question" in first_result and "answer" in first_result and
            first_result.get("confidence", 0) >= self.confidence_threshold):
            return f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"

        return None

    def apply_domain_specific_filtering(self,
                                      context_items: List[Dict[str, Any]],
                                      query: str) -> List[Dict[str, Any]]:
        """Apply QA-specific filtering/ranking"""
        if not context_items:
            return []

        # If boost_exact_matches is enabled, increase confidence for exact matches
        if self.boost_exact_matches:
            for item in context_items:
                if "question" in item and query.lower() in item["question"].lower():
                    # Boost confidence for questions containing the query
                    item["confidence"] = min(1.0, item["confidence"] * 1.2)

                    # For exact matches, boost even more
                    if query.lower() == item["question"].lower():
                        item["confidence"] = min(1.0, item["confidence"] * 1.5)

        # Filter out items below confidence threshold
        filtered_items = [item for item in context_items
                         if item.get("confidence", 0) >= self.confidence_threshold]

        # Sort by confidence score
        filtered_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        return filtered_items
