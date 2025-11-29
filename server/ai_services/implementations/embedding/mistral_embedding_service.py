"""
Mistral embedding service implementation using unified architecture.

This is a migrated version of the Mistral embedding service that uses
the new unified AI services architecture.

Compare with: server/embeddings/mistral.py (old implementation)
"""

import logging
from typing import List, Dict, Any

from ...providers import MistralBaseService
from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class MistralEmbeddingService(EmbeddingService, MistralBaseService):
    """
    Mistral embedding service using unified architecture.

    This implementation leverages:
    1. API key management from MistralBaseService
    2. Client initialization from MistralBaseService
    3. Configuration parsing from base classes
    4. Retry logic from ConnectionManager

    Simplified from old implementation with automatic handling of:
    - API key resolution
    - Client setup
    - Error handling
    - Retry logic
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Mistral embedding service.

        Args:
            config: Configuration dictionary
        """
        # Cooperative initialization keeps base setup/logging single-run
        super().__init__(config, "mistral")

        # Get Mistral-specific configuration
        self.dimensions = self._get_dimensions()  # Default 1024 for mistral-embed
        self.batch_size = self._get_batch_size(default=16)

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Mistral embedding service")

        try:
            response = self.client.embeddings.create(
                model=self.model,
                inputs=[text]
            )

            return response.data[0].embedding

        except Exception as e:
            self._handle_mistral_error(e, "embedding query")
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Mistral embedding service")

        if not texts:
            return []

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    inputs=batch_texts
                )

                # Extract embeddings maintaining order
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                # Log progress for large batches
                if len(texts) > 50 and (i + self.batch_size) % 50 == 0:
                    logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                self._handle_mistral_error(e, "batch embedding")
                raise

        return all_embeddings

    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.

        For Mistral, the mistral-embed model produces 1024-dimensional embeddings.

        Returns:
            The number of dimensions in the embedding vectors
        """
        if self.dimensions:
            return self.dimensions

        # Determine dimensions by generating a test embedding
        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions

        except Exception as e:
            logger.error(f"Failed to determine embedding dimensions: {str(e)}")

            # Fallback: mistral-embed is 1024 dimensions
            self.dimensions = 1024
            return self.dimensions
