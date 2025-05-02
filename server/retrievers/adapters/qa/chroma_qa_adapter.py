"""
ChromaDB-specific QA adapter that matches the original implementation
"""

from typing import Dict, Any, List, Optional
import logging
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING ChromaQAAdapter MODULE")

# Print out registered adapters before we add ours
logger.info(f"Currently registered adapters: {list(DocumentAdapterFactory._registered_adapters.keys()) if hasattr(DocumentAdapterFactory, '_registered_adapters') else 'Unknown'}")

class ChromaQAAdapter(DocumentAdapter):
    """Adapter for question-answer pairs in ChromaDB, matching original implementation"""
    
    def __init__(self, confidence_threshold: float = 0.7, verbose: bool = False):
        self.confidence_threshold = confidence_threshold
        self.verbose = verbose
        logger.info(f"ChromaQAAdapter INITIALIZED with confidence_threshold={confidence_threshold}, verbose={verbose}")
        if self.verbose:
            logger.info("ChromaQAAdapter verbose logging enabled")
        logger.info("ChromaQAAdapter instance created and ready to use")
    
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
        if self.verbose:
            logger.info(f"ChromaQAAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
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
                logger.info(f"ChromaQAAdapter: Formatted QA pair - Question: {metadata['question'][:50]}...")
        else:
            # Otherwise, use the document content
            item["content"] = raw_doc
            
            if self.verbose:
                logger.info(f"ChromaQAAdapter: Formatted regular document - Content: {raw_doc[:50]}...")
            
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
        if self.verbose:
            logger.info(f"ChromaQAAdapter.extract_direct_answer called with {len(context) if context else 0} context items")
            
        if not context:
            if self.verbose:
                logger.info("ChromaQAAdapter: No context items, returning None")
            return None
            
        first_result = context[0]
        
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            
            # Return a formatted answer that includes both question and answer for clarity
            answer = f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
            
            if self.verbose:
                logger.info(f"ChromaQAAdapter: Direct answer found with confidence {first_result.get('confidence')}")
                logger.info(f"ChromaQAAdapter: Question: {first_result['question'][:50]}...")
            
            return answer
        
        if self.verbose:
            logger.info(f"ChromaQAAdapter: No suitable direct answer found. Confidence threshold: {self.confidence_threshold}")
            if "confidence" in first_result:
                logger.info(f"ChromaQAAdapter: Top result confidence: {first_result.get('confidence')}")
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply QA-specific filtering/ranking.
        Required by the DocumentAdapter abstract base class.
        """
        if self.verbose:
            logger.info(f"ChromaQAAdapter.apply_domain_specific_filtering called with {len(context_items)} items and query: {query[:50]}...")
            
        # Original implementation didn't do domain-specific filtering, just sorted by confidence
        if self.verbose:
            logger.info("ChromaQAAdapter: No domain-specific filtering applied, returning items as-is")
            
        return context_items
        
    # Add compatibility method that matches what ChromaRetriever is calling
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match ChromaRetriever's expected interface.
        This is called by ChromaRetriever.apply_domain_filtering.
        """
        if self.verbose:
            logger.info(f"ChromaQAAdapter.apply_domain_filtering called with {len(context_items)} items")
        # Just call our implementation
        return self.apply_domain_specific_filtering(context_items, query)


# Make sure our adapter is the primary one registered for "qa"
logger.info("REGISTERING ChromaQAAdapter AS 'qa'")

# Create factory function with the right config paths
def create_chroma_qa_adapter(config: Dict[str, Any]) -> ChromaQAAdapter:
    """Create a ChromaQAAdapter with settings from configuration"""
    # Use info level
    logger.info("Creating ChromaQAAdapter from config")
    
    # Extract config, supporting both direct chroma and datasources.chroma paths
    verbose = config.get('general', {}).get('verbose', False)
    
    # Look for confidence threshold in several possible locations
    confidence_threshold = 0.7  # Default
    
    if 'datasources' in config and 'chroma' in config['datasources']:
        chroma_config = config['datasources']['chroma']
        confidence_threshold = chroma_config.get('confidence_threshold', confidence_threshold)
    elif 'chroma' in config:
        confidence_threshold = config.get('chroma', {}).get('confidence_threshold', confidence_threshold)
    
    logger.info(f"ChromaQAAdapter parameters: verbose={verbose}, confidence_threshold={confidence_threshold}")
    
    # Create and return the adapter
    return ChromaQAAdapter(confidence_threshold=confidence_threshold, verbose=verbose)

DocumentAdapterFactory.register_adapter("qa", create_chroma_qa_adapter)

# Print the registry after registration to verify
logger.info(f"AFTER REGISTRATION - Available adapters: {list(DocumentAdapterFactory._registered_adapters.keys()) if hasattr(DocumentAdapterFactory, '_registered_adapters') else 'Unknown'}")
logger.info("ChromaQAAdapter module loaded and registered as 'qa'")