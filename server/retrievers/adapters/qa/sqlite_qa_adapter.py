"""
SQLite-specific QA adapter that matches the original implementation
"""

from typing import Dict, Any, List, Optional
import logging
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING SQLiteQAAdapter MODULE")

# Register with the factory only as "sqlite_qa", not as the default "qa"
DocumentAdapterFactory.register_adapter("sqlite_qa", lambda **kwargs: SQLiteQAAdapter(**kwargs))
logger.info(f"Registered SQLiteQAAdapter as 'sqlite_qa'")

class SQLiteQAAdapter(DocumentAdapter):
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
        self.config = config or {}
        logger.info(f"SQLiteQAAdapter INITIALIZED with confidence_threshold={confidence_threshold}, verbose={verbose}")
        if self.verbose:
            logger.info("SQLiteQAAdapter verbose logging enabled")
        logger.info("SQLiteQAAdapter instance created and ready to use")
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        Matches the original SQLiteRetriever._format_metadata implementation.
        
        Args:
            raw_doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        if self.verbose:
            logger.info(f"SQLiteQAAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
        try:
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
                    logger.info(f"SQLiteQAAdapter: Formatted QA pair - Question: {metadata['question'][:50]}...")
            else:
                # Otherwise, use the document content
                item["content"] = raw_doc
                
                if self.verbose:
                    logger.info(f"SQLiteQAAdapter: Formatted regular document - Content: {raw_doc[:50]}...")
                
            return item
            
        except Exception as e:
            logger.error(f"Error formatting document: {str(e)}")
            # Return a minimal valid item to prevent errors
            return {
                "raw_document": raw_doc,
                "content": raw_doc,
                "metadata": metadata.copy() if metadata else {}
            }
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        Matches the original BaseRetriever.get_direct_answer implementation.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        if self.verbose:
            logger.info(f"SQLiteQAAdapter.extract_direct_answer called with {len(context) if context else 0} context items")
            
        try:
            if not context:
                if self.verbose:
                    logger.info("SQLiteQAAdapter: No context items, returning None")
                return None
                
            first_result = context[0]
            
            if ("question" in first_result and "answer" in first_result and 
                first_result.get("confidence", 0) >= self.confidence_threshold):
                
                # Return a formatted answer that includes both question and answer for clarity
                answer = f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
                
                if self.verbose:
                    logger.info(f"SQLiteQAAdapter: Direct answer found with confidence {first_result.get('confidence')}")
                    logger.info(f"SQLiteQAAdapter: Question: {first_result['question'][:50]}...")
                
                return answer
            
            if self.verbose:
                logger.info(f"SQLiteQAAdapter: No suitable direct answer found. Confidence threshold: {self.confidence_threshold}")
                if "confidence" in first_result:
                    logger.info(f"SQLiteQAAdapter: Top result confidence: {first_result.get('confidence')}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting direct answer: {str(e)}")
            return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply QA-specific filtering/ranking.
        Required by the DocumentAdapter abstract base class.
        """
        if self.verbose:
            logger.info(f"SQLiteQAAdapter.apply_domain_specific_filtering called with {len(context_items)} items and query: {query[:50]}...")
            
        try:
            # Original implementation didn't do domain-specific filtering, just sorted by confidence
            if self.verbose:
                logger.info("SQLiteQAAdapter: No domain-specific filtering applied, returning items as-is")
                
            return context_items
            
        except Exception as e:
            logger.error(f"Error applying domain-specific filtering: {str(e)}")
            return context_items
        
    # Add compatibility method that matches what SQLiteRetriever is calling
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match SQLiteRetriever's expected interface.
        This is called by SQLiteRetriever.apply_domain_filtering.
        """
        if self.verbose:
            logger.info(f"SQLiteQAAdapter.apply_domain_filtering called with {len(context_items)} items")
        try:
            # Just call our implementation
            return self.apply_domain_specific_filtering(context_items, query)
        except Exception as e:
            logger.error(f"Error in apply_domain_filtering: {str(e)}")
            return context_items

# Print the registry after registration to verify
logger.info(f"AFTER REGISTRATION - Available adapters: {list(DocumentAdapterFactory._registered_adapters.keys()) if hasattr(DocumentAdapterFactory, '_registered_adapters') else 'Unknown'}")
logger.info("SQLiteQAAdapter module loaded and registered as 'sqlite_qa'") 