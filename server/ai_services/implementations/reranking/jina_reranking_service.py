"""
Jina AI reranking service implementation using unified architecture.

Jina AI provides dedicated reranking models via their API, optimized for
high-quality relevance scoring.
"""

import logging
from typing import Dict, Any, List, Optional

from ...providers import JinaBaseService
from ...services import RerankingService

logger = logging.getLogger(__name__)


class JinaRerankingService(RerankingService, JinaBaseService):
    """
    Jina AI reranking service using the Reranker API.

    Features:
    - Purpose-built reranking models
    - Multilingual support
    - Fast inference
    - Good quality/cost ratio
    - Batch processing support

    Jina AI offers various reranking models optimized for different use cases.
    
    This implementation leverages:
    1. API key management from JinaBaseService
    2. Session initialization from JinaBaseService
    3. Configuration parsing from base classes
    4. Retry logic from ConnectionManager
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Jina AI reranking service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes using cooperative multiple inheritance
        JinaBaseService.__init__(self, config, RerankingService.service_type, "jina")
        RerankingService.__init__(self, config, "jina")

        # Get reranking-specific configuration
        provider_config = self._extract_provider_config()

        # Get API base URL
        if 'api_base' in provider_config:
            self.api_base = provider_config.get('api_base')
        else:
            # JinaBaseService sets base_url to "https://api.jina.ai/v1"
            self.api_base = self.base_url

        self.return_documents = provider_config.get('return_documents', True)

    async def initialize(self) -> bool:
        """
        Initialize the Jina AI reranking service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # JinaBaseService already provides session management
            # Just ensure the base service is initialized
            await super().initialize()

            self.initialized = True
            logger.info(f"Jina AI reranking service initialized with model: {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Jina AI reranking service: {str(e)}")
            return False

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Jina AI's Reranker API.

        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, uses default or returns all)
            _skip_init_check: Internal flag to skip initialization check (used during verify_connection)

        Returns:
            List of dictionaries containing reranked documents with scores.
            Each dictionary contains:
            - 'index': Original index of the document
            - 'text': Document text
            - 'score': Relevance score
        """
        if not _skip_init_check and not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Jina AI reranking service")

        if not documents:
            return []

        # Use top_n from parameter, or fall back to config default
        if top_n is None:
            top_n = self.top_n_default

        try:
            # Prepare request payload
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents
            }

            if top_n is not None:
                payload["top_n"] = top_n

            # Make API request using session from JinaBaseService
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            session = await self._get_session()
            async with session.post(
                f"{self.api_base}/rerank",
                json=payload,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Jina AI API error: {error_text}")
                    raise ValueError(f"Jina AI rerank failed: {error_text}")

                data = await response.json()

                # Parse results
                results = []
                for result in data.get('results', []):
                    results.append({
                        'index': result.get('index', result.get('document_index', 0)),
                        'text': documents[result.get('index', result.get('document_index', 0))],
                        'score': result.get('relevance_score', result.get('score', 0.0))
                    })

                logger.debug(f"Reranked {len(documents)} -> {len(results)} documents")
                return results

        except Exception as e:
            logger.error(f"Error in Jina AI reranking: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """
        Verify the connection to Jina AI's API.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Test with minimal reranking request
            test_query = "test"
            test_docs = ["test document"]

            # Skip init check to avoid infinite recursion during initialization
            results = await self.rerank(test_query, test_docs, top_n=1, _skip_init_check=True)

            if results and len(results) > 0:
                logger.info("Successfully verified Jina AI reranking connection")
                return True
            else:
                logger.error("Received empty results from Jina AI")
                return False

        except Exception as e:
            logger.error(f"Failed to verify Jina AI reranking connection: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the reranking service and release resources.
        """
        # JinaBaseService manages the session, just mark as uninitialized
        self.initialized = False
        logger.info("Jina AI reranking service closed")
