"""
Cohere reranking service implementation using unified architecture.

Cohere provides a dedicated Rerank API endpoint that offers industry-leading
reranking quality with multilingual support.
"""

import logging
from typing import Dict, Any, List, Optional
import asyncio
import aiohttp

from ..providers import CohereBaseService
from ..services import RerankingService

logger = logging.getLogger(__name__)


class CohereRerankingService(RerankingService, CohereBaseService):
    """
    Cohere reranking service using the Rerank API.

    Features:
    - Dedicated reranking API endpoint
    - Multilingual support (100+ languages)
    - High-quality relevance scoring
    - Fast response times
    - Support for top_n filtering

    Cohere offers both English and multilingual reranking models.
    
    This implementation leverages:
    1. API key management from CohereBaseService
    2. Client initialization from CohereBaseService
    3. Configuration parsing from base classes
    4. Retry logic from ConnectionManager
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Cohere reranking service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes using cooperative multiple inheritance
        CohereBaseService.__init__(self, config, RerankingService.service_type, "cohere")
        RerankingService.__init__(self, config, "cohere")

        # Get reranking-specific configuration
        provider_config = self._extract_provider_config()

        # Get API base URL - detect version from base_url
        # CohereBaseService sets base_url to "https://api.cohere.ai" or "https://api.cohere.ai/v2"
        if 'api_base' in provider_config:
            self.api_base = provider_config.get('api_base')
        else:
            # Detect API version from base_url and use appropriate endpoint
            if hasattr(self, 'api_version') and self.api_version == 'v2':
                # v2 API uses /v2 prefix
                if '/v2' in self.base_url:
                    self.api_base = self.base_url
                else:
                    self.api_base = f"{self.base_url}/v2"
            else:
                # v1 API uses /v1 prefix
                self.api_base = f"{self.base_url}/v1"

        self.max_chunks_per_doc = provider_config.get('max_chunks_per_doc', 10)
        self.return_documents = provider_config.get('return_documents', True)

        # Session management for HTTP calls
        self.session = None

    async def initialize(self) -> bool:
        """
        Initialize the Cohere reranking service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Create aiohttp session for rerank API calls
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)

            self.initialized = True
            logger.info(f"Cohere reranking service initialized with model: {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Cohere reranking service: {str(e)}")
            return False

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Cohere's Rerank API.

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
            - 'score': Relevance score (0.0 to 1.0+)
        """
        if not _skip_init_check and not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere reranking service")

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
                "documents": documents,
                "return_documents": self.return_documents
            }

            if top_n is not None:
                payload["top_n"] = top_n

            if self.max_chunks_per_doc:
                payload["max_chunks_per_doc"] = self.max_chunks_per_doc

            # Make API request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with self.session.post(
                f"{self.api_base}/rerank",
                json=payload,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Cohere API error: {error_text}")
                    raise ValueError(f"Cohere rerank failed: {error_text}")

                data = await response.json()

                # Parse results
                results = []
                for result in data.get('results', []):
                    results.append({
                        'index': result['index'],
                        'text': documents[result['index']],
                        'score': result['relevance_score']
                    })

                logger.debug(f"Reranked {len(documents)} -> {len(results)} documents")
                return results

        except Exception as e:
            logger.error(f"Error in Cohere reranking: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """
        Verify the connection to Cohere's API.

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
                logger.info("Successfully verified Cohere reranking connection")
                return True
            else:
                logger.error("Received empty results from Cohere")
                return False

        except Exception as e:
            logger.error(f"Failed to verify Cohere reranking connection: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the reranking service and release resources.
        """
        if self.session:
            await self.session.close()
            self.session = None
        self.initialized = False
        logger.info("Cohere reranking service closed")
