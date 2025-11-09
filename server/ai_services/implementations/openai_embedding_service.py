"""
OpenAI embedding service implementation using unified architecture.

This is a migrated version of the OpenAI embedding service that uses
the new unified AI services architecture, demonstrating the benefits
of code consolidation and reusability.

Compare with: server/embeddings/openai.py (old implementation)
"""

from typing import List, Dict, Any
import asyncio

from ..providers import OpenAIBaseService
from ..services import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService, OpenAIBaseService):
    """
    OpenAI embedding service using unified architecture.

    This implementation is dramatically simpler than the old version because:
    1. API key management handled by OpenAIBaseService
    2. Client initialization handled by OpenAIBaseService
    3. Connection management handled by OpenAIBaseService
    4. Retry logic available from ConnectionManager
    5. Configuration parsing handled by ProviderAIService base class

    Old implementation: ~253 lines with manual everything
    New implementation: ~80 lines focused only on embedding logic
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI embedding service.

        Args:
            config: Configuration dictionary

        Note: All the heavy lifting (API key resolution, client setup, etc.)
              is handled by the base classes!
        """
        # Cooperative initialization to avoid double-running base setup/logging
        super().__init__(config, "openai")

        # Get embedding-specific configuration
        self.dimensions = self._get_dimensions_config() or 1536
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
                raise ValueError("Failed to initialize OpenAI embedding service")

        try:
            # Debug logging
            self.logger.info(f"OpenAIEmbeddingService.embed_query called")
            self.logger.info(f"  self.client = {self.client}")
            self.logger.info(f"  self.client is None: {self.client is None}")
            if self.client:
                self.logger.info(f"  hasattr(self.client, 'embeddings'): {hasattr(self.client, 'embeddings')}")

            # Use the AsyncOpenAI client provided by OpenAIBaseService
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions if (self.model and 'text-embedding-3' in self.model) else None
            )

            return response.data[0].embedding

        except Exception as e:
            self.logger.error(f"Unexpected error during embedding query: {e}")
            self._handle_openai_error(e, "embedding query")
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
                raise ValueError("Failed to initialize OpenAI embedding service")

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                batch_embeddings = await self._embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)

                # Small delay to avoid rate limits
                if i + self.batch_size < len(texts):
                    await asyncio.sleep(0.5)

            except Exception as e:
                self.logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
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
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions if (self.model and 'text-embedding-3' in self.model) else None
            )

            # Sort by index to ensure order matches input order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        except Exception as e:
            self._handle_openai_error(e, "batch embedding")
            raise

    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.

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

            # Fallback to defaults based on model
            if self.model and "ada" in self.model:
                self.dimensions = 1536
            elif self.model and "3-small" in self.model:
                self.dimensions = 1536
            elif self.model and "3-large" in self.model:
                self.dimensions = 3072
            else:
                self.dimensions = 1536  # Default fallback

            return self.dimensions
