"""
Voyage AI reranking service implementation using unified architecture.

Voyage AI provides purpose-built reranking models via their API,
offering good performance and cost-effectiveness.
"""

import logging
from typing import Dict, Any, List, Optional
import asyncio
import aiohttp

from ...services import RerankingService
from ...base import ServiceType

logger = logging.getLogger(__name__)


class VoyageRerankingService(RerankingService):
    """
    Voyage AI reranking service using the Rerank API.

    Features:
    - Purpose-built reranking models
    - Good performance/cost ratio
    - Simple API
    - Fast response times

    Voyage AI offers specialized reranking models optimized for accuracy.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Voyage AI reranking service.

        Args:
            config: Configuration dictionary
        """
        super().__init__(config, "voyage")

        # Get provider-specific configuration
        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("VOYAGE_API_KEY")
        self.api_base = provider_config.get('api_base', 'https://api.voyageai.com/v1')
        self.model = provider_config.get('model', 'rerank-lite-1')
        self.truncation = provider_config.get('truncation', True)

        # Session management
        self.session = None

    async def initialize(self) -> bool:
        """
        Initialize the Voyage AI reranking service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Create aiohttp session
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)

            self.initialized = True
            logger.info(f"Voyage AI reranking service initialized with model: {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Voyage AI reranking service: {str(e)}")
            return False

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Voyage AI's Rerank API.

        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, uses default or returns all)
            _skip_init_check: Internal flag to skip initialization check (used during verify_connection)

        Returns:
            List of dictionaries containing reranked documents with scores.
        """
        if not _skip_init_check and not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Voyage AI reranking service")

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
                "truncation": self.truncation
            }

            if top_n is not None:
                payload["top_k"] = top_n

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
                    logger.error(f"Voyage AI API error: {error_text}")
                    raise ValueError(f"Voyage AI rerank failed: {error_text}")

                data = await response.json()

                # Parse results
                results = []
                for result in data.get('data', []):
                    results.append({
                        'index': result['index'],
                        'text': documents[result['index']],
                        'score': result['relevance_score']
                    })

                logger.debug(f"Reranked {len(documents)} -> {len(results)} documents")
                return results

        except Exception as e:
            logger.error(f"Error in Voyage AI reranking: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """
        Verify the connection to Voyage AI's API.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            test_query = "test"
            test_docs = ["test document"]

            # Skip init check to avoid infinite recursion during initialization
            results = await self.rerank(test_query, test_docs, top_n=1, _skip_init_check=True)

            if results and len(results) > 0:
                logger.info("Successfully verified Voyage AI reranking connection")
                return True
            else:
                logger.error("Received empty results from Voyage AI")
                return False

        except Exception as e:
            logger.error(f"Failed to verify Voyage AI reranking connection: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the reranking service and release resources.
        """
        if self.session:
            await self.session.close()
            self.session = None
        self.initialized = False
        logger.info("Voyage AI reranking service closed")
