"""
Sentence Transformers embedding service implementation using unified architecture.

This service supports both local model inference and remote Hugging Face API,
providing high-performance embeddings from popular open-source models.

Supported models:
- BAAI/bge-m3 (1024 dimensions, multilingual)
- BAAI/bge-large-en-v1.5 (1024 dimensions, English)
- all-MiniLM-L6-v2 (384 dimensions, fast)
- And any sentence-transformers compatible model
"""

import logging
from typing import List, Dict, Any
import asyncio

from ..providers import SentenceTransformersBaseService
from ..services import EmbeddingService

logger = logging.getLogger(__name__)


class SentenceTransformersEmbeddingService(EmbeddingService, SentenceTransformersBaseService):
    """
    Sentence Transformers embedding service using unified architecture.

    This implementation provides:
    1. Local model inference with GPU support
    2. Remote Hugging Face Inference API support
    3. Automatic device detection (CUDA/MPS/CPU)
    4. Model caching using Hugging Face defaults
    5. Batch processing for efficiency
    6. Optional L2 normalization
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Sentence Transformers embedding service.

        Args:
            config: Configuration dictionary

        Note: Model loading and device detection are handled by
              SentenceTransformersBaseService!
        """
        # Cooperative initialization keeps base setup/logging running once
        super().__init__(config, "sentence_transformers")

        # Get embedding-specific configuration
        self.dimensions = self._get_dimensions()
        self.batch_size = self._get_batch_size(default=32)

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector

        Raises:
            ValueError: If service not initialized or text is empty
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Sentence Transformers embedding service")

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if self.mode == "local":
            return await self._embed_query_local(text)
        else:
            return await self._embed_query_remote(text)

    async def _embed_query_local(self, text: str) -> List[float]:
        """
        Generate embeddings using local model.

        Args:
            text: The query text to embed

        Returns:
            Embedding vector
        """
        async def _embed():
            # Run in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self.model_instance.encode(
                    text,
                    normalize_embeddings=self.normalize_embeddings,
                    convert_to_numpy=True
                )
            )

            # Convert numpy array to list
            embedding_list = embedding.tolist()

            # Verify dimensions if configured
            if self.dimensions and len(embedding_list) != self.dimensions:
                logger.warning(
                    f"Expected {self.dimensions} dimensions but got {len(embedding_list)}"
                )

            return embedding_list

        # Use retry handler for robustness
        return await self.retry_handler.execute_with_retry(_embed)

    async def _embed_query_remote(self, text: str) -> List[float]:
        """
        Generate embeddings using Hugging Face Inference API.

        Args:
            text: The query text to embed

        Returns:
            Embedding vector
        """
        async def _embed():
            import aiohttp

            url = f"{self.base_url}/{self.model}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "inputs": text,
                "options": {
                    "wait_for_model": True
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Error from Hugging Face API: {error_text}")
                        raise ValueError(f"Failed to get embeddings: {error_text}")

                    # HF API returns the embedding directly as array
                    embedding = await response.json()

                    if not isinstance(embedding, list):
                        raise ValueError("Invalid response from Hugging Face API")

                    # Normalize if requested
                    if self.normalize_embeddings:
                        embedding = self._normalize_embedding(embedding)

                    return embedding

        return await self.retry_handler.execute_with_retry(_embed)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents with batch processing.

        Processes documents in batches for better performance.

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors (each a list of floats)

        Raises:
            ValueError: If service not initialized
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Sentence Transformers embedding service")

        if not texts:
            return []

        if self.mode == "local":
            return await self._embed_documents_local(texts)
        else:
            return await self._embed_documents_remote(texts)

    async def _embed_documents_local(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents using local model.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            try:
                # Run in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                batch_embeddings = await loop.run_in_executor(
                    None,
                    lambda: self.model_instance.encode(
                        batch,
                        normalize_embeddings=self.normalize_embeddings,
                        convert_to_numpy=True,
                        show_progress_bar=False
                    )
                )

                # Convert numpy array to list of lists
                batch_embeddings_list = batch_embeddings.tolist()
                all_embeddings.extend(batch_embeddings_list)

                # Log progress for large batches
                if len(texts) > 50 and (i + self.batch_size) % 50 == 0:
                    logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                logger.error(f"Batch processing failed at index {i}: {e}")

                # Fall back to individual processing for this batch
                for text in batch:
                    try:
                        embedding = await self._embed_query_local(text)
                        all_embeddings.append(embedding)
                    except Exception as e:
                        logger.error(f"Failed to embed document: {e}")
                        # Use zero vector as fallback
                        fallback_dims = self.dimensions or 768
                        all_embeddings.append([0.0] * fallback_dims)

        return all_embeddings

    async def _embed_documents_remote(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents using remote API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            # Create tasks for parallel processing
            tasks = [self._embed_query_remote(text) for text in batch]

            try:
                batch_embeddings = await asyncio.gather(*tasks, return_exceptions=True)

                # Handle any exceptions in the batch
                for j, result in enumerate(batch_embeddings):
                    if isinstance(result, Exception):
                        logger.error(f"Failed to embed document {i+j}: {result}")
                        # Retry individually for failed embeddings
                        try:
                            result = await self._embed_query_remote(batch[j])
                        except Exception as e:
                            logger.error(f"Retry failed for document {i+j}: {e}")
                            # Use zero vector as fallback
                            fallback_dims = self.dimensions or 768
                            result = [0.0] * fallback_dims

                    all_embeddings.append(result)

                # Log progress for large batches
                if len(texts) > 50 and (i + self.batch_size) % 50 == 0:
                    logger.debug(
                        f"Processed {min(i + self.batch_size, len(texts))}/{len(texts)} documents"
                    )

            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                # Fall back to sequential processing
                for text in batch:
                    try:
                        embedding = await self._embed_query_remote(text)
                        all_embeddings.append(embedding)
                    except Exception as e:
                        logger.error(f"Failed to embed document: {e}")
                        fallback_dims = self.dimensions or 768
                        all_embeddings.append([0.0] * fallback_dims)

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
        try:
            test_embedding = await self.embed_query("test")
            self.dimensions = len(test_embedding)
            return self.dimensions
        except Exception as e:
            logger.error(f"Failed to determine dimensions: {str(e)}")
            # Use a reasonable fallback based on common models
            fallback = 768
            logger.warning(f"Using fallback dimensions: {fallback}")
            self.dimensions = fallback
            return fallback

    def _normalize_embedding(self, embedding: List[float]) -> List[float]:
        """
        L2 normalize an embedding vector.

        Args:
            embedding: The embedding vector to normalize

        Returns:
            Normalized embedding vector
        """
        import math

        # Calculate L2 norm
        norm = math.sqrt(sum(x * x for x in embedding))

        if norm == 0:
            return embedding

        # Normalize
        return [x / norm for x in embedding]
