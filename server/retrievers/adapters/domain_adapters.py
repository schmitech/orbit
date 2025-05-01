"""
Domain-specific adapters for vector DB retrievers
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union

class DocumentAdapter(ABC):
    """
    Interface for adapting documents to specific domain representations.
    This allows extending retrievers to different domains without changing core code.
    """
    
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
    
    def __init__(self, confidence_threshold: float = 0.7, boost_exact_matches: bool = False):
        self.confidence_threshold = confidence_threshold
        self.boost_exact_matches = boost_exact_matches
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for QA domain"""
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),
        }
        
        if "question" in metadata and "answer" in metadata:
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
        # If boost_exact_matches is enabled, increase confidence for exact matches
        if self.boost_exact_matches and context_items:
            for item in context_items:
                if "question" in item and query.lower() in item["question"].lower():
                    # Boost confidence for questions containing the query
                    item["confidence"] = min(1.0, item["confidence"] * 1.2)
                
        return context_items


class GenericDocumentAdapter(DocumentAdapter):
    """Adapter for generic document retrieval (not QA-specific)"""
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format document for general retrieval"""
        item = {
            "raw_document": raw_doc,
            "content": raw_doc,
            "metadata": metadata.copy(),
        }
        
        # Extract title if available
        if "title" in metadata:
            item["title"] = metadata["title"]
            
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """Generic documents don't have direct answers"""
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """Apply generic content filtering"""
        # Could implement document importance weighting here
        return context_items


class DocumentAdapterFactory:
    """Factory for creating document adapters"""
    
    _registered_adapters = {}
    
    @classmethod
    def register_adapter(cls, name: str, adapter_class):
        """Register a document adapter"""
        cls._registered_adapters[name] = adapter_class
    
    @classmethod
    def create_adapter(cls, adapter_type: str, **kwargs):
        """Create an adapter instance"""
        if adapter_type not in cls._registered_adapters:
            raise ValueError(f"Unknown adapter type: {adapter_type}")
            
        return cls._registered_adapters[adapter_type](**kwargs)


# Register built-in adapters
DocumentAdapterFactory.register_adapter("qa", QADocumentAdapter)
DocumentAdapterFactory.register_adapter("generic", GenericDocumentAdapter)