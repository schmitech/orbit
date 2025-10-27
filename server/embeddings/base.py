"""
Base classes and factory for embedding services.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union

class EmbeddingService(ABC):
    """
    Abstract base class for embedding services.
    All embedding providers should implement this interface.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the embedding service with configuration.
        
        Args:
            config: Configuration dictionary specific to this embedding provider
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.initialized = False
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a query string.
        
        Args:
            text: The query text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        pass
    
    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.
        
        Args:
            texts: A list of document texts to embed
            
        Returns:
            A list of embedding vectors (each a list of floats)
        """
        pass
    
    @abstractmethod
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings produced by this service.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        pass
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        pass


class EmbeddingServiceFactory:
    """
    Factory class for creating embedding service instances based on configuration.
    Implements singleton pattern to share embedding services across adapters.
    """
    
    _instances: Dict[str, EmbeddingService] = {}
    _lock = None
    
    @classmethod
    def _get_lock(cls):
        """Get or create the lock for thread safety."""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()
        return cls._lock
    
    @classmethod
    def create_embedding_service(cls, config: Dict[str, Any], provider_name: Optional[str] = None) -> EmbeddingService:
        """
        Create or return a cached embedding service instance based on configuration.
        Implements singleton pattern to share embedding services across adapters.
        
        Args:
            config: The full application configuration
            provider_name: Optional specific provider name to override the one in config
            
        Returns:
            An initialized embedding service instance (shared singleton)
            
        Raises:
            ValueError: If the specified provider is not supported
        """
        # Get the embedding provider - either specified or from config
        if not provider_name:
            provider_name = config.get('embedding', {}).get('provider', 'ollama')
        
        # Create a cache key that includes provider name and relevant config
        cache_key = cls._create_cache_key(provider_name, config)
        
        # Check if we already have this instance
        with cls._get_lock():
            if cache_key in cls._instances:
                logger = logging.getLogger(__name__)
                logger.debug(f"Reusing cached embedding service: {provider_name}")
                return cls._instances[cache_key]
            
            # Create new instance
            logger = logging.getLogger(__name__)
            logger.debug(f"Creating new embedding service instance: {provider_name}")
            instance = cls._create_new_instance(provider_name, config)
            cls._instances[cache_key] = instance
            return instance
    
    @staticmethod
    def _create_cache_key(provider_name: str, config: Dict[str, Any]) -> str:
        """Create a cache key for the embedding service based on provider and config."""
        # Include relevant config parameters that would affect the service instance
        provider_config = config.get('embeddings', {}).get(provider_name, {})
        
        # Create a key based on provider and key config parameters
        # For most providers, the host/endpoint and model are the distinguishing factors
        host = provider_config.get('host', provider_config.get('base_url', ''))
        model = provider_config.get('model', '')
        
        return f"{provider_name}:{host}:{model}"
    
    @staticmethod
    def _create_new_instance(provider_name: str, config: Dict[str, Any]) -> EmbeddingService:
        """
        Create a new embedding service instance.

        NOTE: This now uses the new unified AI services architecture!
        The old embeddings implementations have been migrated.
        """
        # Lazy import the service class dynamically based on provider name
        # This allows the system to work even if some providers are not installed

        # Map provider names to class names
        class_name_map = {
            'openai': 'OpenAIEmbeddingService',
            'ollama': 'OllamaEmbeddingService',
            'cohere': 'CohereEmbeddingService',
            'mistral': 'MistralEmbeddingService',
            'jina': 'JinaEmbeddingService',
            'llama_cpp': 'LlamaCppEmbeddingService'
        }

        if provider_name not in class_name_map:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")

        class_name = class_name_map[provider_name]

        # Try to import the specific service class
        try:
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(
                f"Embedding provider '{provider_name}' is not available. "
                f"This may be because required dependencies are not installed. "
                f"Error: {e}"
            )

        # Pass the full config - the new services handle config extraction
        return service_class(config)
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached embedding service instances. Useful for testing or reloading."""
        with cls._get_lock():
            # Close all cached instances
            for instance in cls._instances.values():
                try:
                    if hasattr(instance, 'close'):
                        import asyncio
                        if asyncio.iscoroutinefunction(instance.close):
                            # For async close methods, we can't await here, so just skip
                            pass
                        else:
                            instance.close()
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Error closing embedding service: {e}")
            
            cls._instances.clear()
    
    @classmethod
    def get_cached_instances(cls) -> Dict[str, EmbeddingService]:
        """Get all currently cached embedding service instances. Useful for debugging."""
        with cls._get_lock():
            return cls._instances.copy()
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached embedding services."""
        with cls._get_lock():
            return {
                "total_cached_instances": len(cls._instances),
                "cached_providers": list(cls._instances.keys()),
                "memory_info": f"{len(cls._instances)} embedding service instances cached"
            }