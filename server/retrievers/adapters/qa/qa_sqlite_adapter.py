"""
SQLite-specific QA adapter that matches the original implementation
"""

from typing import Dict, Any, List, Optional
import logging
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING QASqliteAdapter MODULE")

# Register with the factory as both "sqlite_qa" and the default "qa"
DocumentAdapterFactory.register_adapter("sqlite_qa", lambda **kwargs: QASqliteAdapter(**kwargs))
logger.info(f"Registered QASqliteAdapter as 'sqlite_qa'")

class QASqliteAdapter(DocumentAdapter):
    """Adapter for question-answer pairs in SQLite, matching original implementation"""
    
    def __init__(self, confidence_threshold: float = 0.5, verbose: bool = False, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize the adapter with configurable confidence threshold.
        
        Args:
            confidence_threshold: Minimum confidence score to consider a match (default: 0.5)
            verbose: Whether to enable verbose logging
            config: Optional configuration dictionary, not used directly but needed for compatibility
            **kwargs: Additional keyword arguments that might be passed
        """
        self.confidence_threshold = confidence_threshold
        self.verbose = verbose
        logger.info(f"QASqliteAdapter INITIALIZED with confidence_threshold={confidence_threshold}, verbose={verbose}")
        if self.verbose:
            logger.info("QASqliteAdapter verbose logging enabled")
        logger.info("QASqliteAdapter instance created and ready to use")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        
        Args:
            raw_doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        if self.verbose:
            logger.info(f"QASqliteAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
        # If it's already a QA document, return it as is
        if "question" in metadata and "answer" in metadata:
            return metadata
            
        # Create the base item with confidence
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),  # Include full metadata
        }
        
        # Set the content field based on document type
        if "question" in metadata and "answer" in metadata:
            # If it's a QA pair, set content to the question and answer together
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
            
            if self.verbose:
                logger.info(f"QASqliteAdapter: Formatted QA pair - Question: {metadata['question'][:50]}...")
        else:
            # Otherwise, use the document content
            item["content"] = raw_doc
            
            if self.verbose:
                logger.info(f"QASqliteAdapter: Formatted regular document - Content: {raw_doc[:50]}...")
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        if self.verbose:
            logger.info(f"QASqliteAdapter.extract_direct_answer called with {len(context) if context else 0} context items")
            
        if not context:
            if self.verbose:
                logger.info("QASqliteAdapter: No context items, returning None")
            return None
            
        first_result = context[0]
        
        # Check if we have a QA document with sufficient confidence
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            
            # Return a formatted answer that includes both question and answer for clarity
            answer = f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
            
            if self.verbose:
                logger.info(f"QASqliteAdapter: Direct answer found with confidence {first_result.get('confidence')}")
                logger.info(f"QASqliteAdapter: Question: {first_result['question'][:50]}...")
            
            return answer
        
        if self.verbose:
            logger.info(f"QASqliteAdapter: No suitable direct answer found. Confidence threshold: {self.confidence_threshold}")
            if "confidence" in first_result:
                logger.info(f"QASqliteAdapter: Top result confidence: {first_result.get('confidence')}")
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply QA-specific filtering/ranking.
        Required by the DocumentAdapter abstract base class.
        """
        if self.verbose:
            logger.info(f"QASqliteAdapter.apply_domain_specific_filtering called with {len(context_items)} items and query: {query[:50]}...")
            
        # Filter out items below confidence threshold
        filtered_items = [
            item for item in context_items 
            if item.get("confidence", 0) >= self.confidence_threshold
        ]
        
        if self.verbose:
            logger.info(f"QASqliteAdapter: Filtered {len(context_items) - len(filtered_items)} items below confidence threshold")
            
        return filtered_items
        
    # Add compatibility method that matches what SQLiteRetriever is calling
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match SQLiteRetriever's expected interface.
        This is called by SQLiteRetriever.apply_domain_filtering.
        """
        if self.verbose:
            logger.info(f"QASqliteAdapter.apply_domain_filtering called with {len(context_items)} items")
        # Just call our implementation
        return self.apply_domain_specific_filtering(context_items, query) 