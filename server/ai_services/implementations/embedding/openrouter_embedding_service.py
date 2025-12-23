"""
OpenRouter embedding service implementation using the native OpenRouter SDK.

This implementation uses the official OpenRouter Python SDK for embedding generation.
OpenRouter provides access to various embedding models through a unified API.

SDK Documentation: https://openrouter.ai/docs/sdks/python/embeddings
"""

import logging
from typing import List, Dict, Any, Optional

from openrouter import OpenRouter

from ...services import EmbeddingService


logger = logging.getLogger(__name__)


class OpenRouterEmbeddingService(EmbeddingService):
    """
    OpenRouter embedding service using the native OpenRouter SDK.

    OpenRouter is a unified gateway to multiple AI providers, including
    embedding models from OpenAI, Cohere, and others.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the OpenRouter embedding service."""
        super().__init__(config, "openrouter")

        # Get embedding-specific configuration
        self.dimensions = self._get_dimensions_config()
        self.batch_size = self._get_batch_size(default=10)

        # Resolve API key
        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide in configuration."
            )

        # Get model from config
        self.model = self._get_model()
        if not self.model:
            raise ValueError("OpenRouter embedding model must be specified in configuration.")

        # Client will be initialized in initialize()
        self.client: Optional[OpenRouter] = None

        logger.info(f"Configured OpenRouter embedding service with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the OpenRouter embedding service."""
        try:
            if self.initialized:
                return True

            # Create OpenRouter client
            self.client = OpenRouter(api_key=self.api_key)

            self.initialized = True
            logger.info(f"Initialized OpenRouter embedding service with model {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter embedding service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """Verify connection to OpenRouter."""
        try:
            if not self.client:
                logger.error("OpenRouter client is not initialized.")
                return False

            # Make a minimal test request
            response = await self.client.embeddings.generate_async(
                input="test",
                model=self.model
            )

            if response and response.data:
                logger.debug("OpenRouter embedding connection verified successfully")
                return True

            return False

        except Exception as e:
            logger.error(f"OpenRouter embedding connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the OpenRouter service and release resources."""
        if self.client:
            self.client = None

        self.initialized = False
        logger.debug("Closed OpenRouter embedding service")

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
                raise ValueError("Failed to initialize OpenRouter embedding service")

        try:
            response = await self.client.embeddings.generate_async(
                input=text,
                model=self.model
            )

            return response.data[0].embedding

        except Exception as e:
            logger.error(f"OpenRouter embedding error: {str(e)}")
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
                raise ValueError("Failed to initialize OpenRouter embedding service")

        if not texts:
            return []

        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                response = await self.client.embeddings.generate_async(
                    input=batch_texts,
                    model=self.model
                )

                # Extract embeddings from response
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                # Log progress for large batches
                if len(texts) > 50 and (i + self.batch_size) % 50 == 0:
                    logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                raise

        return all_embeddings

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
            logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback
            self.dimensions = 1536
            return self.dimensions
