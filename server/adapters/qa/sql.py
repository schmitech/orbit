"""
Generic SQL QA adapter that works with any SQL provider
"""

from typing import Dict, Any, List, Optional
import logging
from adapters.base import DocumentAdapter
from adapters.factory import DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING QASQLAdapter MODULE")

# Register with the factory as both "sql_qa" and the default "qa"
DocumentAdapterFactory.register_adapter("sql_qa", lambda **kwargs: QASQLAdapter(**kwargs))
logger.info(f"Registered QASQLAdapter as 'sql_qa'")

class QASQLAdapter(DocumentAdapter):
    """Generic adapter for question-answer pairs in SQL databases"""
    
    def __init__(self, confidence_threshold: float = 0.5, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize the adapter with configurable confidence threshold.

        Args:
            confidence_threshold: Minimum confidence score to consider a match (default: 0.5)
            config: Optional configuration dictionary
            **kwargs: Additional keyword arguments
        """
        self.confidence_threshold = confidence_threshold
        self.config = config or {}
        logger.info(f"QASQLAdapter INITIALIZED with confidence_threshold={confidence_threshold}")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        
        Args:
            raw_doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        logger.debug(f"QASQLAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
        # Create the base item
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),
        }
        
        # Handle different document formats
        if "question" in metadata and "answer" in metadata:
            # QA pair format
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
        elif "title" in metadata and "content" in metadata:
            # Title + content format
            item["content"] = f"Title: {metadata['title']}\nContent: {metadata['content']}"
            item["title"] = metadata["title"]
        else:
            # Generic content format
            item["content"] = raw_doc
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        if not context:
            return None
            
        first_result = context[0]
        
        # Check if we have a QA document with sufficient confidence
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            return f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply QA-specific filtering/ranking.
        """
        # Filter out items below confidence threshold
        return [
            item for item in context_items 
            if item.get("confidence", 0) >= self.confidence_threshold
        ]
        
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match SQLRetriever's expected interface.
        """
        return self.apply_domain_specific_filtering(context_items, query) 