"""
Base retriever interface and factory for pluggable document retrieval
"""

from abc import ABC, abstractmethod
import logging
from typing import Dict, Any, List, Optional, Type
import importlib
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)

class BaseRetriever(ABC):
    """Base abstract class that all retriever implementations should extend"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize required services and connections."""
        pass
        
    @abstractmethod
    async def close(self) -> None:
        """Close any open services and connections."""
        pass
        
    @abstractmethod
    async def get_relevant_context(self, 
                                  query: str, 
                                  api_key: Optional[str] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The user's query
            api_key: Optional API key for accessing resources
            collection_name: Optional collection/database/index name
            **kwargs: Additional parameters specific to each retriever implementation
            
        Returns:
            A list of context items filtered by relevance
        """
        pass
        
    def get_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        return None


class RetrieverFactory:
    """Factory for creating and managing retriever instances"""
    
    _registered_retrievers: Dict[str, Type[BaseRetriever]] = {}
    
    @classmethod
    def register_retriever(cls, name: str, retriever_class: Type[BaseRetriever]) -> None:
        """
        Register a retriever implementation
        
        Args:
            name: Unique identifier for the retriever
            retriever_class: The retriever class to register
        """
        cls._registered_retrievers[name] = retriever_class
        logger.info(f"Registered retriever implementation: {name}")
        
    @classmethod
    def create_retriever(cls, 
                        retriever_type: str, 
                        config: Dict[str, Any],
                        **kwargs) -> BaseRetriever:
        """
        Create a retriever instance of the specified type
        
        Args:
            retriever_type: Type of retriever to create
            config: Configuration dictionary
            **kwargs: Additional arguments to pass to the retriever constructor
            
        Returns:
            An instance of the requested retriever
            
        Raises:
            ValueError: If the retriever type is not registered
        """
        # Check if retriever is registered
        if retriever_type not in cls._registered_retrievers:
            # Try to dynamically import the module
            try:
                module_path = f"retrievers.{retriever_type}_retriever"
                module = importlib.import_module(module_path)
                retriever_class_name = f"{retriever_type.capitalize()}Retriever"
                retriever_class = getattr(module, retriever_class_name)
                cls.register_retriever(retriever_type, retriever_class)
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to dynamically load retriever '{retriever_type}': {str(e)}")
                raise ValueError(f"Retriever type '{retriever_type}' is not registered")
        
        # Create and return the retriever instance
        try:
            retriever_class = cls._registered_retrievers[retriever_type]
            return retriever_class(config=config, **kwargs)
        except Exception as e:
            logger.error(f"Failed to create retriever of type '{retriever_type}': {str(e)}")
            raise