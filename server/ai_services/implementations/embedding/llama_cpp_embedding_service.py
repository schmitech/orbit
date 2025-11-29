"""
Llama.cpp embedding service implementation using unified architecture.

This is a migrated version of the llama.cpp embedding service that uses
the new unified AI services architecture, supporting both API mode and
direct GGUF model loading.

Compare with: server/embeddings/llama_cpp.py (old implementation)
"""

import logging
from typing import List, Dict, Any
import asyncio

from ...providers.llama_cpp_base import LlamaCppBaseService
from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class LlamaCppEmbeddingService(EmbeddingService, LlamaCppBaseService):
    """
    Llama.cpp embedding service using unified architecture.

    This implementation supports two modes:
    1. API mode: Uses OpenAI-compatible llama.cpp server
    2. Direct mode: Loads GGUF models directly using llama-cpp-python

    Benefits of the new architecture:
    1. Model loading handled by LlamaCppBaseService
    2. Configuration parsing handled by ProviderAIService base class
    3. Retry logic available from RetryHandler
    4. Connection management handled by base classes

    Old implementation: ~301 lines with manual everything
    New implementation: ~150 lines focused only on embedding logic
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the llama.cpp embedding service.

        Args:
            config: Configuration dictionary

        Note: Model loading and configuration handled by base classes!
        """
        # Cooperative initialization prevents duplicate base setup/logging
        super().__init__(config, "llama_cpp")

        # Get embedding-specific configuration
        self.dimensions = self._get_dimensions()
        self.batch_size = self._get_batch_size(default=8)

    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            await self.initialize()

        try:
            if self.mode == "api":
                return await self._embed_query_api(text)
            else:
                return await self._embed_query_direct(text)

        except Exception as e:
            self._handle_llama_cpp_error(e, "embedding query")
            raise

    async def _embed_query_api(self, text: str) -> List[float]:
        """
        Generate embeddings using API mode (OpenAI-compatible server).

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding

    async def _embed_query_direct(self, text: str) -> List[float]:
        """
        Generate embeddings using direct mode (GGUF model).

        Args:
            text: The query text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        # Run the embedding generation in a separate thread
        embedding = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self._generate_embedding,
            text
        )
        return embedding

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text using llama.cpp.
        This runs in a separate thread.

        Args:
            text: The text to embed

        Returns:
            A list of floats representing the embedding vector
        """
        try:
            # Get embedding from llama.cpp model
            if self.embed_type == 'llama_embedding':
                # Use the embedded embedding function (standard llama2 embedding)
                embedding = self.llama_model.embed(text)
            else:
                # Fall back to using last hidden state (experimental)
                embeddings = self.llama_model.create_embedding(text)
                embedding = embeddings['embedding']

            return embedding
        except Exception as e:
            logger.error(f"Error in llama.cpp _generate_embedding: {str(e)}")
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
            await self.initialize()

        try:
            if self.mode == "api":
                return await self._embed_documents_api(texts)
            else:
                return await self._embed_documents_direct(texts)

        except Exception as e:
            self._handle_llama_cpp_error(e, "batch embedding")
            raise

    async def _embed_documents_api(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using API mode (OpenAI-compatible server).

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors
        """
        all_embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            response = await self.client.embeddings.create(
                model=self.model,
                input=batch_texts
            )

            # Sort by index to ensure order matches input order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            batch_embeddings = [item.embedding for item in sorted_data]
            all_embeddings.extend(batch_embeddings)

            # Small delay to avoid overwhelming the server
            if i + self.batch_size < len(texts):
                await asyncio.sleep(0.1)

        return all_embeddings

    async def _embed_documents_direct(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using direct mode (GGUF model).

        Args:
            texts: A list of document texts to embed

        Returns:
            A list of embedding vectors
        """
        all_embeddings = []

        # Process documents in batches
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            # Run the batch embedding generation in a separate thread
            batch_embeddings = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._generate_batch_embeddings,
                batch_texts
            )
            all_embeddings.extend(batch_embeddings)

            # Add a small delay to avoid overwhelming the CPU/GPU
            if i + self.batch_size < len(texts):
                await asyncio.sleep(0.1)

        return all_embeddings

    def _generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        This runs in a separate thread.

        Args:
            texts: The list of texts to embed

        Returns:
            A list of embedding vectors
        """
        batch_embeddings = []
        for text in texts:
            try:
                embedding = self._generate_embedding(text)
                batch_embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Error embedding text '{text[:30]}...': {str(e)}")
                raise

        return batch_embeddings

    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings produced by this service.

        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        if self.dimensions:
            return self.dimensions

        # Get a test embedding to determine dimensions
        try:
            # Use a short test string to determine embedding dimensions
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions
        except Exception as e:
            logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback - many GGUF embedding models use 4096 dimensions
            self.dimensions = 4096
            logger.warning(f"Using fallback embedding dimensions: {self.dimensions}")
            return self.dimensions
