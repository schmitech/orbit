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
    """
    
    @staticmethod
    def create_embedding_service(config: Dict[str, Any], provider_name: Optional[str] = None) -> EmbeddingService:
        """
        Create an embedding service instance based on configuration.
        
        Args:
            config: The full application configuration
            provider_name: Optional specific provider name to override the one in config
            
        Returns:
            An initialized embedding service instance
            
        Raises:
            ValueError: If the specified provider is not supported
        """
        # Get the embedding provider - either specified or from config
        if not provider_name:
            provider_name = config.get('embedding', {}).get('provider', 'ollama')
        
        # Import the appropriate embedding service
        if provider_name == 'ollama':
            from embeddings.ollama import OllamaEmbeddingService
            provider_config = config.get('embeddings', {}).get('ollama', {})
            return OllamaEmbeddingService(provider_config)
        elif provider_name == 'huggingface':
            from embeddings.huggingface import HuggingFaceEmbeddingService
            provider_config = config.get('embeddings', {}).get('huggingface', {})
            return HuggingFaceEmbeddingService(provider_config)
        elif provider_name == 'openai':
            from embeddings.openai import OpenAIEmbeddingService
            provider_config = config.get('embeddings', {}).get('openai', {})
            return OpenAIEmbeddingService(provider_config)
        elif provider_name == 'bedrock':
            from embeddings.bedrock import BedrockEmbeddingService
            provider_config = config.get('embeddings', {}).get('bedrock', {})
            return BedrockEmbeddingService(provider_config)
        elif provider_name == 'cohere':
            from embeddings.cohere import CohereEmbeddingService
            provider_config = config.get('embeddings', {}).get('cohere', {})
            return CohereEmbeddingService(provider_config)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")