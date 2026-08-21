"""
OpenRouter reranking service implementation using unified architecture.

OpenRouter provides a unified rerank endpoint that proxies to reranking
models from multiple providers (e.g. Cohere).

API Documentation: https://openrouter.ai/docs/api/api-reference/rerank/submit-a-rerank-request
"""

import logging
from typing import Dict, Any, List, Optional
import aiohttp

from ...services import RerankingService

logger = logging.getLogger(__name__)


class OpenRouterRerankingService(RerankingService):
    """
    OpenRouter reranking service using OpenRouter's unified Rerank API.
    """

    SUPPORTS_USAGE_REPORTING = True

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "openrouter")

        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide in configuration."
            )

        self.api_base = provider_config.get('api_base', 'https://openrouter.ai/api/v1')
        self.model = provider_config.get('model', 'cohere/rerank-v3.5')

        self.session = None

    async def initialize(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)

            self.initialized = True
            logger.debug(f"Initialized OpenRouter reranking service with model {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter reranking service: {str(e)}")
            return False

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False,
        usage_sink: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using OpenRouter's Rerank API.

        Returns:
            List of dictionaries containing reranked documents with scores.
        """
        if not _skip_init_check and not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize OpenRouter reranking service")

        if not documents:
            return []

        if top_n is None:
            top_n = self.top_n_default

        try:
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
            }

            if top_n is not None:
                payload["top_n"] = top_n

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
                    logger.error(f"OpenRouter API error: {error_text}")
                    raise ValueError(f"OpenRouter rerank failed: {error_text}")

                data = await response.json()

                usage = data.get('usage')
                if usage is not None:
                    self._report_media_usage(usage_sink, "search_units", usage.get('search_units'))

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
            logger.error(f"Error in OpenRouter reranking: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        try:
            test_query = "test"
            test_docs = ["test document"]

            results = await self.rerank(test_query, test_docs, top_n=1, _skip_init_check=True)

            if results and len(results) > 0:
                logger.info("Successfully verified OpenRouter reranking connection")
                return True
            else:
                logger.error("Received empty results from OpenRouter")
                return False

        except Exception as e:
            logger.error(f"Failed to verify OpenRouter reranking connection: {str(e)}")
            return False

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
        self.initialized = False
        logger.info("OpenRouter reranking service closed")
