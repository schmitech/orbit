"""
Base class for reranker services.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class RerankerService(ABC):
    """
    Abstract base class for reranker services.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the reranker service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.initialized = False
        self.logger = None  # Should be set by implementing class
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the reranker service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Rerank documents based on their relevance to the query.
        
        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, returns all)
            
        Returns:
            List of dictionaries containing reranked documents with scores
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the reranker service and release any resources.
        """
        pass 