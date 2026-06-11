"""
Cohere embedding service implementation using unified architecture.

This is a migrated version of the Cohere embedding service that uses
the new unified AI services architecture.

Compare with: server/embeddings/cohere.py (old implementation)
"""

import logging
from typing import List, Dict, Any

from ...providers import CohereBaseService
from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class CohereEmbeddingService(EmbeddingService, CohereBaseService):
    """
    Cohere embedding service using unified architecture.

    This implementation leverages:
    1. API key management from CohereBaseService
    2. Client initialization from CohereBaseService
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
        Initialize the Cohere embedding service.

        Args:
            config: Configuration dictionary
        """
        # Cooperative initialization keeps base setup/logging single-run
        super().__init__(config, "cohere")

        # Get Cohere-specific configuration
        self.dimensions = self._get_dimensions()
        self.batch_size = self._get_batch_size(default=96)  # Cohere supports large batches
        self.input_type = self._get_input_type("search_document")
        self.truncate = self._get_truncate("NONE")

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        await self._ensure_initialized("Cohere embedding service")

        try:
            # Use input_type="search_query" for queries
            response = await self.client.embed(
                texts=[text],
                model=self.model,
                input_type="search_query",  # Optimized for search queries
                truncate=self.truncate
            )

            return response.embeddings[0]

        except Exception as e:
            self._handle_cohere_error(e, "embedding query")
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.

        Cohere supports large batch sizes, so we can process many documents at once.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)
        """
        await self._ensure_initialized("Cohere embedding service")

        if not texts:
            return []

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                # Use input_type="search_document" for documents
                response = await self.client.embed(
                    texts=batch_texts,
                    model=self.model,
                    input_type=self.input_type,  # search_document for documents
                    truncate=self.truncate
                )

                all_embeddings.extend(response.embeddings)

                # Log progress for large batches
                if len(texts) > 50 and (i + self.batch_size) % 50 == 0:
                    logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                self._handle_cohere_error(e, "batch embedding")
                raise

        return all_embeddings

    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.

        For Cohere, dimensions are typically model-specific and configured.

        Returns:
            The number of dimensions in the embedding vectors
        """
        # embed-english-light-v3.0 is 384 dimensions; other models default to 1024
        fallback = 384 if (self.model and "embed-english-light-v3.0" in self.model) else 1024
        return await self._resolve_dimensions(fallback)
