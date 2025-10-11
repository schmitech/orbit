"""
Cohere embedding service implementation using unified architecture.

This is a migrated version of the Cohere embedding service that uses
the new unified AI services architecture.

Compare with: server/embeddings/cohere.py (old implementation)
"""

from typing import List, Dict, Any

from ..providers import CohereBaseService
from ..services import EmbeddingService


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
        # Initialize base classes
        CohereBaseService.__init__(self, config, EmbeddingService.service_type)
        EmbeddingService.__init__(self, config, "cohere")

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
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere embedding service")

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
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere embedding service")

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
                    self.logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                self.logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
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
        if self.dimensions:
            return self.dimensions

        # Determine dimensions by generating a test embedding
        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions

        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")

            # Fallback based on common Cohere models
            if "embed-english-v3.0" in self.model or "embed-multilingual-v3.0" in self.model:
                self.dimensions = 1024
            elif "embed-english-light-v3.0" in self.model:
                self.dimensions = 384
            else:
                self.dimensions = 1024  # Default fallback

            return self.dimensions
