"""
Embedding service interface and base implementations.

This module defines the common interface for all embedding services,
providing a unified API regardless of the underlying provider.
"""

from abc import abstractmethod
from typing import List, Dict, Any, Optional
import logging

from ..base import ProviderAIService, ServiceType


class EmbeddingService(ProviderAIService):
    """
    Base class for all embedding services.

    This class defines the common interface that all embedding service
    implementations must follow, regardless of provider (OpenAI, Ollama,
    Cohere, etc.).

    Key Methods:
        - embed_query: Generate embeddings for a single query
        - embed_documents: Generate embeddings for multiple documents
        - get_dimensions: Get the dimensionality of embeddings

    Configuration Support:
        - Configurable endpoints via config
        - Batch processing configuration
        - Dimension configuration
    """

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the embedding service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'openai', 'ollama')
        """
        super().__init__(config, ServiceType.EMBEDDING, provider_name)
        self.dimensions: Optional[int] = None
        self.batch_size: int = self._get_batch_size()

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        This is typically used for search queries or single text inputs.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector

        Raises:
            ValueError: If the service is not initialized or text is empty
            Exception: For provider-specific errors

        Example:
            >>> service = OpenAIEmbeddingService(config)
            >>> await service.initialize()
            >>> embedding = await service.embed_query("Hello world")
            >>> len(embedding)
            1536
        """
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.

        This method should implement batch processing for efficiency.
        The implementation should respect the configured batch_size.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)

        Raises:
            ValueError: If the service is not initialized or texts is empty
            Exception: For provider-specific errors

        Example:
            >>> service = OpenAIEmbeddingService(config)
            >>> await service.initialize()
            >>> embeddings = await service.embed_documents(["Doc 1", "Doc 2"])
            >>> len(embeddings)
            2
        """
        pass

    @abstractmethod
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.

        This may be configured or determined dynamically by generating
        a test embedding.

        Returns:
            The number of dimensions in the embedding vectors

        Example:
            >>> service = OpenAIEmbeddingService(config)
            >>> await service.initialize()
            >>> dims = await service.get_dimensions()
            >>> dims
            1536
        """
        pass

    def _get_batch_size(self, default: int = 10) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default batch size if not configured

        Returns:
            Configured batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def _get_dimensions_config(self) -> Optional[int]:
        """
        Get configured dimensions.

        Returns:
            Configured dimensions or None
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('dimensions')

    async def embed_query_with_fallback(
        self,
        text: str,
        fallback_value: Optional[List[float]] = None
    ) -> List[float]:
        """
        Embed a query with optional fallback on error.

        This is a convenience method that handles errors gracefully.

        Args:
            text: The query text to embed
            fallback_value: Optional fallback embedding to return on error

        Returns:
            Embedding vector or fallback value

        Example:
            >>> embedding = await service.embed_query_with_fallback(
            ...     "text",
            ...     fallback_value=[0.0] * 1536
            ... )
        """
        try:
            return await self.embed_query(text)
        except Exception as e:
            self.logger.error(f"Failed to embed query, using fallback: {str(e)}")
            if fallback_value is not None:
                return fallback_value
            raise

    async def embed_documents_with_retry(
        self,
        texts: List[str],
        retry_failed: bool = True
    ) -> List[List[float]]:
        """
        Embed documents with automatic retry for failed items.

        This method attempts to embed all documents and retries any
        that fail individually.

        Args:
            texts: List of texts to embed
            retry_failed: Whether to retry failed embeddings individually

        Returns:
            List of embeddings (may contain zero vectors for failed items)

        Example:
            >>> embeddings = await service.embed_documents_with_retry(texts)
        """
        try:
            return await self.embed_documents(texts)
        except Exception as e:
            if not retry_failed:
                raise

            self.logger.warning(
                f"Batch embedding failed, retrying individually: {str(e)}"
            )

            # Retry each document individually
            embeddings = []
            dimensions = await self.get_dimensions()

            for text in texts:
                try:
                    embedding = await self.embed_query(text)
                    embeddings.append(embedding)
                except Exception as e:
                    self.logger.error(f"Failed to embed document: {str(e)}")
                    # Use zero vector as fallback
                    embeddings.append([0.0] * dimensions)

            return embeddings


class EmbeddingResult:
    """
    Structured result for embedding operations.

    This class provides a standardized way to return embedding results
    with metadata.
    """

    def __init__(
        self,
        embeddings: List[List[float]],
        dimensions: int,
        model: str,
        provider: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize embedding result.

        Args:
            embeddings: List of embedding vectors
            dimensions: Dimensionality of embeddings
            model: Model used for embeddings
            provider: Provider name
            metadata: Optional metadata
        """
        self.embeddings = embeddings
        self.dimensions = dimensions
        self.model = model
        self.provider = provider
        self.metadata = metadata or {}

    def __len__(self) -> int:
        """Return number of embeddings."""
        return len(self.embeddings)

    def __getitem__(self, index: int) -> List[float]:
        """Get embedding by index."""
        return self.embeddings[index]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'embeddings': self.embeddings,
            'dimensions': self.dimensions,
            'model': self.model,
            'provider': self.provider,
            'metadata': self.metadata
        }


# Helper function for service creation
def create_embedding_service(
    provider: str,
    config: Dict[str, Any]
) -> EmbeddingService:
    """
    Factory function to create an embedding service.

    This is a convenience function that will use the AIServiceFactory
    once services are registered.

    Args:
        provider: Provider name (e.g., 'openai', 'ollama')
        config: Configuration dictionary

    Returns:
        Embedding service instance

    Example:
        >>> service = create_embedding_service('openai', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.EMBEDDING,
        provider,
        config
    )
