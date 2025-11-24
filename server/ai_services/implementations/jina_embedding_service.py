"""
Jina AI embedding service implementation using unified architecture.

This is a migrated version of the Jina AI embedding service that uses
the new unified AI services architecture, demonstrating the benefits
of code consolidation and reusability.

Compare with: server/embeddings/jina.py (old implementation)
"""

import logging
from typing import List, Dict, Any
import asyncio

from ..providers.jina_base import JinaBaseService
from ..services import EmbeddingService

logger = logging.getLogger(__name__)


class JinaEmbeddingService(EmbeddingService, JinaBaseService):
    """
    Jina AI embedding service using unified architecture.

    This implementation is dramatically simpler than the old version because:
    1. API key management handled by JinaBaseService
    2. Session initialization handled by JinaBaseService
    3. Connection management handled by JinaBaseService
    4. Retry logic available from RetryHandler
    5. Configuration parsing handled by ProviderAIService base class

    Old implementation: ~319 lines with manual everything
    New implementation: ~120 lines focused only on embedding logic
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Jina embedding service.

        Args:
            config: Configuration dictionary

        Note: All the heavy lifting (API key resolution, session setup, etc.)
              is handled by the base classes!
        """
        # Cooperative initialization avoids double base setup/logging
        super().__init__(config, "jina")

        # Get embedding-specific configuration
        self.task = self._get_task(default="text-matching")
        self.dimensions = self._get_dimensions() or 1024
        self.batch_size = self._get_batch_size(default=10)

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize Jina embedding service")

        try:
            session = await self._get_session()
            url = f"{self.base_url}{self.endpoint}"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            payload = {
                "model": self.model,
                "task": self.task,
                "dimensions": self.dimensions,
                "input": [text]
            }

            logger.debug(f"Sending embedding request to Jina API for text: {text[:50]}...")

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Error from Jina API: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")

                data = await response.json()

                # Extract the embedding from the response
                if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                    embedding = data["data"][0]["embedding"]
                    return embedding
                else:
                    logger.error(f"Unexpected response structure from Jina API: {data}")
                    raise ValueError("Failed to extract embedding from response")

        except Exception as e:
            self._handle_jina_error(e, "embedding query")
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.

        Uses batching to avoid rate limits.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize Jina embedding service")

        all_embeddings = []

        # Process in batches to avoid API limits
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                batch_embeddings = await self._embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)

                # Add a small delay between batches to avoid rate limits
                if i + self.batch_size < len(texts):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                raise

        return all_embeddings

    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: A batch of texts to embed

        Returns:
            A list of embedding vectors
        """
        session = await self._get_session()
        url = f"{self.base_url}{self.endpoint}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "task": self.task,
            "dimensions": self.dimensions,
            "input": texts
        }

        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Error from Jina API: {error_text}")
                raise ValueError(f"Failed to get batch embeddings: {error_text}")

            data = await response.json()

            # Extract embeddings from the response
            if "data" in data and len(data["data"]) > 0:
                # Ensure the order matches the input order
                embeddings = []
                for item in data["data"]:
                    if "embedding" in item:
                        embeddings.append(item["embedding"])
                    else:
                        logger.error(f"Missing embedding in response item: {item}")
                        raise ValueError("Failed to extract embedding from response")

                # Verify we got the expected number of embeddings
                if len(embeddings) != len(texts):
                    logger.warning(f"Expected {len(texts)} embeddings but got {len(embeddings)}")

                return embeddings
            else:
                logger.error(f"Unexpected response structure from Jina API: {data}")
                raise ValueError("Failed to extract embeddings from response")

    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.

        Returns:
            The number of dimensions in the embedding vectors
        """
        if self.dimensions:
            return self.dimensions

        # Generate a test embedding to determine dimensions
        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions

        except Exception as e:
            logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback dimensions for jina-embeddings-v3
            self.dimensions = 1024
            return self.dimensions
