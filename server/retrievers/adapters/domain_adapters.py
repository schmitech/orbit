"""
domain adapters for retrievers with registry integration
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
import logging

# Import the registry
from retrievers.adapters.registry import ADAPTER_REGISTRY

# Configure logging
logger = logging.getLogger(__name__)

class DocumentAdapter(ABC):
    """
    Interface for adapting documents to specific domain representations.
    This allows extending retrievers to different domains without changing core code.
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
            A formatted document representation
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
            context_items: Context items from vector search
            query: The user's query
            
        Returns:
            Filtered and/or reranked context items
        """
        pass


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
        self.verbose = self.config.get('verbose', False)
        
        if self.verbose:
            logger.info(f"Initialized QA Document Adapter with confidence threshold: {self.confidence_threshold}")
    
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
        self.verbose = self.config.get('verbose', False)
        
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


class DocumentAdapterFactory:
    """Factory for creating document adapters"""
    
    _registered_adapters = {}
    
    @classmethod
    def register_adapter(cls, adapter_type: str, factory_func):
        """
        Register a new adapter type with its factory function.
        
        Args:
            adapter_type: Type identifier for the adapter
            factory_func: Function that creates the adapter instance
        """
        cls._registered_adapters[adapter_type.lower()] = factory_func
        logger.info(f"Registered adapter type: {adapter_type}")
    
    @classmethod
    def create_adapter(cls, adapter_type: str, **kwargs) -> DocumentAdapter:
        """
        Create a document adapter instance.
        
        Args:
            adapter_type: Type of adapter to create (e.g., 'qa', 'generic')
            **kwargs: Additional arguments to pass to the adapter
            
        Returns:
            A document adapter instance
            
        Raises:
            ValueError: If the adapter type is not supported
        """
        adapter_type = adapter_type.lower()
        
        # Try to get from registered adapters first
        if adapter_type in cls._registered_adapters:
            return cls._registered_adapters[adapter_type](**kwargs)
            
        # Fall back to built-in adapters
        if adapter_type == 'qa':
            return QADocumentAdapter(**kwargs)
        elif adapter_type == 'generic':
            return GenericDocumentAdapter(**kwargs)
        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")


# Register adapters with the registry
def register_adapters():
    """Register all built-in adapters with the registry"""
    logger.info("Registering built-in domain adapters...")
    
    # Register adapters for all supported datasources
    for datasource in ['sqlite', 'chroma', 'qdrant', 'postgres']:
        # Register QA document adapter with default config
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource=datasource,
            adapter_name="qa",
            implementation='retrievers.adapters.domain_adapters.QADocumentAdapter',
            config={
                'confidence_threshold': 0.7,
                'boost_exact_matches': False,
                'verbose': False
            }
        )
        logger.info(f"Registered QA adapter for {datasource}")
        
        # Register Generic document adapter with default config
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource=datasource,
            adapter_name="generic",
            implementation='retrievers.adapters.domain_adapters.GenericDocumentAdapter',
            config={
                'confidence_threshold': 0.3,
                'verbose': False
            }
        )
        logger.info(f"Registered Generic adapter for {datasource}")
    
    logger.info("Built-in domain adapters registration complete")

# Register adapters when module is imported
register_adapters()