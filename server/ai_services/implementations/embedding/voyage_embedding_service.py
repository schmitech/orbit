"""
Voyage AI embedding service implementation using unified architecture.

Uses the Voyage AI REST API for embeddings, following the same HTTP pattern
as the Voyage reranking service.
"""

import logging
from typing import List, Dict, Any
import asyncio
import aiohttp

from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class VoyageEmbeddingService(EmbeddingService):
    """
    Voyage AI embedding service using the Embeddings API.

    Features:
    - Purpose-built embedding models (voyage-3, voyage-3-lite, voyage-code-3)
    - Separate input_type for queries vs documents
    - Good performance/cost ratio
    - Simple REST API via aiohttp
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Voyage AI embedding service."""
        super().__init__(config, "voyage")

        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("VOYAGE_API_KEY")
        self.api_base = provider_config.get('api_base', 'https://api.voyageai.com/v1')
        self.model = provider_config.get('model', 'voyage-3')
        self.dimensions = self._get_dimensions_config() or 1024
        self.batch_size = self._get_batch_size(default=10)
        self.truncation = provider_config.get('truncation', True)

        self.session = None

        logger.debug(
            f"VoyageEmbeddingService initialized: model={self.model}, "
            f"dimensions={self.dimensions}, batch_size={self.batch_size}, "
            f"api_base={self.api_base}"
        )

    async def initialize(self) -> bool:
        """Initialize the Voyage AI embedding service."""
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            self.session = aiohttp.ClientSession(timeout=timeout)
            self.initialized = True
            logger.info(f"Voyage AI embedding service initialized with model: {self.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Voyage AI embedding service: {e}")
            return False

    async def embed_query(self, text: str) -> List[float]:
        """Generate embeddings for a single query text."""
        if not self.initialized:
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize Voyage AI embedding service")

        try:
            logger.debug(
                f"VoyageEmbeddingService.embed_query: model={self.model}, "
                f"text_length={len(text)}, text_preview={text[:80]!r}"
            )

            embedding = await self._call_api([text], input_type="query")

            logger.debug(
                f"VoyageEmbeddingService.embed_query: returned {len(embedding[0])} dimensions"
            )
            return embedding[0]

        except Exception as e:
            logger.error(f"VoyageEmbeddingService.embed_query failed: {e}")
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple documents with batching."""
        if not self.initialized:
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize Voyage AI embedding service")

        if not texts:
            return []

        logger.debug(
            f"VoyageEmbeddingService.embed_documents: model={self.model}, "
            f"total_texts={len(texts)}, batch_size={self.batch_size}"
        )

        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                batch_num = i // self.batch_size + 1
                total_batches = (len(texts) + self.batch_size - 1) // self.batch_size
                logger.debug(
                    f"VoyageEmbeddingService.embed_documents: processing batch "
                    f"{batch_num}/{total_batches}, texts_in_batch={len(batch_texts)}"
                )

                batch_embeddings = await self._call_api(batch_texts, input_type="document")
                all_embeddings.extend(batch_embeddings)

                logger.debug(
                    f"VoyageEmbeddingService.embed_documents: batch returned "
                    f"{len(batch_embeddings)} embeddings, "
                    f"dims={len(batch_embeddings[0]) if batch_embeddings else 'N/A'}"
                )

                if i + self.batch_size < len(texts):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(
                    f"VoyageEmbeddingService.embed_documents: batch {batch_num} failed: {e}"
                )
                raise

        logger.debug(
            f"VoyageEmbeddingService.embed_documents: completed, "
            f"total_embeddings={len(all_embeddings)}"
        )
        return all_embeddings

    async def _call_api(self, texts: List[str], input_type: str = "document") -> List[List[float]]:
        """
        Call the Voyage AI embeddings API.

        Args:
            texts: List of texts to embed
            input_type: "query" or "document"

        Returns:
            List of embedding vectors
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "input": texts,
            "input_type": input_type,
            "truncation": self.truncation
        }

        async with self.session.post(
            f"{self.api_base}/embeddings",
            json=payload,
            headers=headers
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Voyage AI API error: {error_text}")
                raise ValueError(f"Voyage AI embedding failed: {error_text}")

            data = await response.json()

            if "data" not in data or not data["data"]:
                raise ValueError(f"Unexpected response structure from Voyage AI: {data}")

            # Sort by index to ensure order matches input
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]

    async def get_dimensions(self) -> int:
        """Get the dimensionality of the embeddings."""
        if self.dimensions:
            return self.dimensions

        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions

        except Exception as e:
            logger.error(f"Failed to determine embedding dimensions: {e}")
            # Defaults based on common Voyage models
            if self.model and "lite" in self.model:
                self.dimensions = 512
            else:
                self.dimensions = 1024
            return self.dimensions

    async def verify_connection(self) -> bool:
        """Verify the connection to Voyage AI's API."""
        try:
            result = await self.embed_query("test")
            if result and len(result) > 0:
                logger.info("Successfully verified Voyage AI embedding connection")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to verify Voyage AI embedding connection: {e}")
            return False

    async def close(self) -> None:
        """Close the embedding service and release resources."""
        if self.session:
            await self.session.close()
            self.session = None
        self.initialized = False
        logger.info("Voyage AI embedding service closed")
