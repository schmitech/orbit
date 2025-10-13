"""
Ollama embedding service implementation using unified architecture.

This is a migrated version of the Ollama embedding service that uses
the new unified AI services architecture, integrating with existing
ollama_utils for maximum compatibility.

Compare with: server/embeddings/ollama.py (old implementation)
"""

from typing import List, Dict, Any
import asyncio

from ..providers import OllamaBaseService
from ..services import EmbeddingService


class OllamaEmbeddingService(EmbeddingService, OllamaBaseService):
    """
    Ollama embedding service using unified architecture.

    This implementation is simpler than the old version because:
    1. Ollama utilities integration handled by OllamaBaseService
    2. Configuration parsing handled by base classes
    3. Retry logic inherited from OllamaBaseService
    4. Connection verification handled by base classes
    5. Model warm-up handled by OllamaBaseService

    Old implementation: ~348 lines with complex retry and warmup logic
    New implementation: ~100 lines focused only on embedding logic
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama embedding service.

        Args:
            config: Configuration dictionary

        Note: All Ollama-specific utilities (retry, warmup, etc.) are
              handled by OllamaBaseService!
        """
        # Cooperative initialization keeps base setup/logging running once
        super().__init__(config, "ollama")

        # Get embedding-specific configuration
        self.dimensions = self._get_dimensions()  # From OllamaBaseService
        self.batch_size = self._get_batch_size(default=5)

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text with retry logic.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama embedding service")

        async def _embed():
            session = await self.session_manager.get_session()
            url = f"{self.base_url}/api/embeddings"

            payload = {
                "model": self.model,
                "prompt": text
            }

            # Try to set dimensions if configured (some models support this)
            if self.dimensions:
                payload["options"] = {
                    "num_ctx": self.dimensions,
                    "embedding_size": self.dimensions
                }

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Ollama: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")

                data = await response.json()
                embedding = data.get('embedding', [])

                # Verify we got a valid embedding
                if not embedding or not isinstance(embedding, list) or len(embedding) == 0:
                    raise ValueError("Received invalid embedding from Ollama")

                # Check if dimensions match configuration
                actual_dims = len(embedding)
                if self.dimensions and actual_dims != self.dimensions:
                    # Resize if needed
                    embedding = self._resize_embedding(embedding, self.dimensions)

                return embedding

        # Use Ollama's retry handler
        return await self.execute_with_retry(_embed)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents with retry logic.

        Processes documents in parallel batches for better performance.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama embedding service")

        if not texts:
            return []

        # Process in parallel batches
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            # Create tasks for parallel processing
            tasks = [self.embed_query(text) for text in batch]

            # Wait for all tasks in this batch to complete
            try:
                batch_embeddings = await asyncio.gather(*tasks, return_exceptions=True)

                # Handle any exceptions in the batch
                for j, result in enumerate(batch_embeddings):
                    if isinstance(result, Exception):
                        self.logger.error(f"Failed to embed document {i+j}: {result}")
                        # Retry individually for failed embeddings
                        try:
                            result = await self.embed_query(batch[j])
                        except Exception as e:
                            self.logger.error(f"Retry failed for document {i+j}: {e}")
                            # Use zero vector as fallback
                            result = [0.0] * (self.dimensions or 768)

                    all_embeddings.append(result)

                # Log progress for large batches
                if len(texts) > 20 and (i + self.batch_size) % 20 == 0:
                    self.logger.debug(f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents")

            except Exception as e:
                self.logger.error(f"Batch processing failed: {e}")
                # Fall back to sequential processing
                for text in batch:
                    try:
                        embedding = await self.embed_query(text)
                        all_embeddings.append(embedding)
                    except Exception as e:
                        self.logger.error(f"Failed to embed document: {e}")
                        all_embeddings.append([0.0] * (self.dimensions or 768))

        return all_embeddings

    async def get_dimensions(self) -> int:
        """
        Determine the dimensionality of the embeddings.

        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        if self.dimensions:
            return self.dimensions

        # Create a test embedding to determine dimensions
        async def _get_dims():
            session = await self.session_manager.get_session()
            url = f"{self.base_url}/api/embeddings"
            payload = {
                "model": self.model,
                "prompt": "test"
            }

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    # Use fallback if error
                    fallback = 768
                    self.logger.warning(f"Using fallback dimensions: {fallback}")
                    self.dimensions = fallback
                    return self.dimensions

                data = await response.json()
                embedding = data.get('embedding', [])
                self.dimensions = len(embedding)
                return self.dimensions

        try:
            return await self.execute_with_retry(_get_dims)
        except Exception as e:
            self.logger.error(f"Failed to determine dimensions: {str(e)}")
            fallback = 768
            self.dimensions = fallback
            return fallback

    def _resize_embedding(self, embedding: List[float], target_size: int) -> List[float]:
        """
        Resize an embedding vector to match the target dimensions.

        Args:
            embedding: The original embedding vector
            target_size: The target number of dimensions

        Returns:
            Resized embedding vector
        """
        current_size = len(embedding)

        if current_size == target_size:
            return embedding
        elif current_size > target_size:
            # Truncate
            return embedding[:target_size]
        else:
            # Pad with zeros
            padded = embedding.copy()
            padded.extend([0.0] * (target_size - current_size))
            return padded
