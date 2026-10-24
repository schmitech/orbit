"""
Gemini embedding service implementation using unified architecture.

Uses the google-genai SDK for embedding via client.models.embed_content().
"""

from typing import Any
import asyncio
import logging

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class GeminiEmbeddingService(EmbeddingService, GoogleBaseService):
    """
    Gemini embedding service using unified architecture.

    Uses Google's gemini-embedding-2-preview model via the google-genai SDK.
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the Gemini embedding service."""
        GoogleBaseService.__init__(self, config, ServiceType.EMBEDDING, "gemini")

        self.dimensions = self._get_dimensions_config() or 3072
        self.batch_size = self._get_batch_size(default=10)

        self._genai_client = None

        logger.debug(
            f"GeminiEmbeddingService initialized: model={self.model}, "
            f"dimensions={self.dimensions}, batch_size={self.batch_size}"
        )

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            from google import genai
            import os

            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key

            self._genai_client = genai.Client()
        return self._genai_client

    async def embed_query(self, text: str) -> list[float]:
        """Generate embeddings for a single query text."""
        await self._ensure_initialized("Gemini embedding service")

        try:
            client = self._get_client()
            logger.debug(
                f"GeminiEmbeddingService.embed_query: model={self.model}, "
                f"text_length={len(text)}, text_preview={text[:80]!r}"
            )

            result = await asyncio.to_thread(
                client.models.embed_content,
                model=self.model,
                contents=text,
            )

            embedding = result.embeddings[0].values
            logger.debug(
                f"GeminiEmbeddingService.embed_query: returned {len(embedding)} dimensions"
            )
            return embedding

        except Exception as e:
            logger.error(f"GeminiEmbeddingService.embed_query failed: {e}")
            self._handle_google_error(e, "embedding query")
            raise

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple documents with batching."""
        await self._ensure_initialized("Gemini embedding service")

        if not texts:
            return []

        logger.debug(
            f"GeminiEmbeddingService.embed_documents: model={self.model}, "
            f"total_texts={len(texts)}, batch_size={self.batch_size}"
        )

        batches = [texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        total_batches = len(batches)
        # Cap concurrent in-flight batches to avoid hammering the API the way
        # the old sequential 0.5s inter-batch delay did.
        semaphore = asyncio.Semaphore(3)
        failed = asyncio.Event()

        async def _embed_batch(batch_index: int, batch_texts: list[str]) -> list[list[float]]:
            async with semaphore:
                if failed.is_set():
                    return []
                try:
                    client = self._get_client()
                    logger.debug(
                        f"GeminiEmbeddingService.embed_documents: processing batch "
                        f"{batch_index + 1}/{total_batches}, texts_in_batch={len(batch_texts)}"
                    )

                    result = await asyncio.to_thread(
                        client.models.embed_content,
                        model=self.model,
                        contents=batch_texts,
                    )

                    batch_embeddings = [emb.values for emb in result.embeddings]
                    logger.debug(
                        f"GeminiEmbeddingService.embed_documents: batch returned "
                        f"{len(batch_embeddings)} embeddings, "
                        f"dims={len(batch_embeddings[0]) if batch_embeddings else 'N/A'}"
                    )
                    return batch_embeddings
                except Exception as e:
                    failed.set()
                    logger.error(
                        f"GeminiEmbeddingService.embed_documents: batch {batch_index + 1} failed: {e}"
                    )
                    self._handle_google_error(e, "batch embedding")
                    raise

        tasks = [asyncio.create_task(_embed_batch(idx, batch)) for idx, batch in enumerate(batches)]
        # Cancelling a task awaiting to_thread does not stop its synchronous
        # SDK call. Let started calls finish, while failed prevents queued
        # batches from making new requests.
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in batch_results:
            if isinstance(result, BaseException):
                raise result
        all_embeddings = [emb for batch in batch_results for emb in batch]

        logger.debug(
            f"GeminiEmbeddingService.embed_documents: completed, "
            f"total_embeddings={len(all_embeddings)}"
        )
        return all_embeddings

    async def get_dimensions(self) -> int:
        """Get the dimensionality of the embeddings."""
        # Default for gemini-embedding-2-preview
        return await self._resolve_dimensions(3072)
