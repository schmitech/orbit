"""
ChromaDB-specific QA adapter that matches the original implementation
"""

from typing import Dict, Any, List, Optional
import logging
from adapters.base import DocumentAdapter
from adapters.factory import DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING ChromaQAAdapter MODULE")

# Register with the factory only as "chroma_qa", not as the default "qa"
DocumentAdapterFactory.register_adapter("chroma_qa", lambda **kwargs: ChromaQAAdapter(**kwargs))
logger.info("Registered ChromaQAAdapter as 'chroma_qa'")

class ChromaQAAdapter(DocumentAdapter):
    """Adapter for question-answer pairs in ChromaDB, matching original implementation"""
    
    def __init__(self, confidence_threshold: float = 0.7, config: Dict[str, Any] = None, **kwargs):
        """
        Initialize the adapter with configurable confidence threshold.

        Args:
            confidence_threshold: Minimum confidence score to consider a match (default: 0.7)
            config: Optional configuration dictionary, not used directly but needed for compatibility
            **kwargs: Additional keyword arguments that might be passed
        """
        self.confidence_threshold = confidence_threshold
        logger.info(f"ChromaQAAdapter INITIALIZED with confidence_threshold={confidence_threshold}")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        Matches the original QAChromaRetriever._format_metadata implementation.
        
        Args:
            raw_doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        logger.debug(f"ChromaQAAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
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
            
            logger.debug(f"ChromaQAAdapter: Formatted QA pair - Question: {metadata['question'][:50]}...")
        else:
            # Otherwise, use the document content
            item["content"] = raw_doc
            
            logger.debug(f"ChromaQAAdapter: Formatted regular document - Content: {raw_doc[:50]}...")
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        Matches the original BaseRetriever.get_direct_answer implementation.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        logger.debug(f"ChromaQAAdapter.extract_direct_answer called with {len(context) if context else 0} context items")
            
        if not context:
            logger.debug("ChromaQAAdapter: No context items, returning None")
            return None
            
        first_result = context[0]
        
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            
            # Return a formatted answer that includes both question and answer for clarity
            answer = f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
            
            logger.debug(f"ChromaQAAdapter: Direct answer found with confidence {first_result.get('confidence')}")
            logger.debug(f"ChromaQAAdapter: Question: {first_result['question'][:50]}...")
            
            return answer
        
        logger.debug(f"ChromaQAAdapter: No suitable direct answer found. Confidence threshold: {self.confidence_threshold}")
        if "confidence" in first_result:
            logger.debug(f"ChromaQAAdapter: Top result confidence: {first_result.get('confidence')}")
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply QA-specific filtering/ranking.
        Required by the DocumentAdapter abstract base class.
        """
        logger.debug(f"ChromaQAAdapter.apply_domain_specific_filtering called with {len(context_items)} items and query: {query[:50]}...")
            
        # Original implementation didn't do domain-specific filtering, just sorted by confidence
        logger.debug("ChromaQAAdapter: No domain-specific filtering applied, returning items as-is")
            
        return context_items
        
    # Add compatibility method that matches what ChromaRetriever is calling
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match ChromaRetriever's expected interface.
        This is called by ChromaRetriever.apply_domain_filtering.
        """
        logger.debug(f"ChromaQAAdapter.apply_domain_filtering called with {len(context_items)} items")
        # Just call our implementation
        return self.apply_domain_specific_filtering(context_items, query)

# Print the registry after registration to verify
logger.info(f"AFTER REGISTRATION - Available adapters: {list(DocumentAdapterFactory._registered_adapters.keys()) if hasattr(DocumentAdapterFactory, '_registered_adapters') else 'Unknown'}")
logger.info("ChromaQAAdapter module loaded and registered as 'chroma_qa'")