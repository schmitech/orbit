"""
Reranking service interface and base implementations.

This module defines the common interface for all reranking services,
providing a unified API regardless of the underlying provider.
"""

from abc import abstractmethod
from typing import List, Dict, Any, Optional
import logging

from ..base import ProviderAIService, ServiceType


class RerankingService(ProviderAIService):
    """
    Base class for all reranking services.

    This class defines the common interface that all reranking service
    implementations must follow, regardless of provider (Ollama, Cohere, etc.).

    Key Methods:
        - rerank: Rerank documents based on relevance to a query

    Configuration Support:
        - Configurable endpoints via config
        - Top-n configuration
        - Batch size configuration
    """

    # Class-level service type for compatibility with provider base classes
    service_type = ServiceType.RERANKING

    def _get_batch_size(self, default: int = 5) -> int:
        """
        Get batch size configuration for reranking.

        Args:
            default: Default batch size if not configured

        Returns:
            Configured batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the reranking service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'ollama', 'cohere')
        """
        super().__init__(config, ServiceType.RERANKING, provider_name)
        self.top_n_default: Optional[int] = self._get_top_n_default()
        self.batch_size: int = self._get_batch_size(default=5)

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents based on their relevance to the query.

        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, uses default or returns all)

        Returns:
            List of dictionaries containing reranked documents with scores.
            Each dictionary should have at least:
            - 'index': Original index of the document
            - 'text': Document text
            - 'score': Relevance score

        Example:
            >>> service = OllamaRerankingService(config)
            >>> await service.initialize()
            >>> results = await service.rerank(
            ...     "Python programming",
            ...     ["Python is a language", "Java is also a language"],
            ...     top_n=1
            ... )
            >>> results[0]['text']
            'Python is a language'
        """
        pass

    def _get_top_n_default(self) -> Optional[int]:
        """
        Get default top_n configuration.

        Returns:
            Default top_n value or None
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_n')

    async def rerank_with_scores(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        min_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents and filter by minimum score.

        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return
            min_score: Minimum score threshold (0.0 to 1.0)

        Returns:
            List of reranked documents with scores >= min_score

        Example:
            >>> results = await service.rerank_with_scores(
            ...     "machine learning",
            ...     docs,
            ...     top_n=10,
            ...     min_score=0.5
            ... )
        """
        results = await self.rerank(query, documents, top_n)

        if min_score is not None:
            results = [r for r in results if r.get('score', 0) >= min_score]

        return results


class RerankingResult:
    """
    Structured result for reranking operations.

    This class provides a standardized way to return reranking results
    with metadata.
    """

    def __init__(
        self,
        results: List[Dict[str, Any]],
        query: str,
        model: str,
        provider: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize reranking result.

        Args:
            results: List of reranked document dictionaries
            query: Query used for reranking
            model: Model used for reranking
            provider: Provider name
            metadata: Optional metadata
        """
        self.results = results
        self.query = query
        self.model = model
        self.provider = provider
        self.metadata = metadata or {}

    def __len__(self) -> int:
        """Return number of results."""
        return len(self.results)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        """Get result by index."""
        return self.results[index]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'results': self.results,
            'query': self.query,
            'model': self.model,
            'provider': self.provider,
            'metadata': self.metadata
        }

    def get_top_documents(self, n: int) -> List[str]:
        """
        Get top n document texts.

        Args:
            n: Number of documents to return

        Returns:
            List of document texts
        """
        return [r['text'] for r in self.results[:n]]

    def get_scores(self) -> List[float]:
        """
        Get all scores.

        Returns:
            List of scores
        """
        return [r.get('score', 0.0) for r in self.results]


# Helper function for service creation
def create_reranking_service(
    provider: str,
    config: Dict[str, Any]
) -> RerankingService:
    """
    Factory function to create a reranking service.

    Args:
        provider: Provider name (e.g., 'ollama', 'cohere')
        config: Configuration dictionary

    Returns:
        Reranking service instance

    Example:
        >>> service = create_reranking_service('ollama', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.RERANKING,
        provider,
        config
    )
