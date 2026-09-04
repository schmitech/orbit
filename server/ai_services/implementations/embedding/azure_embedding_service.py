"""
Azure OpenAI embedding service implementation.
"""

from typing import Any
import asyncio
import logging

from ...base import ServiceType
from ...providers import AzureBaseService
from ...providers.usage_reporting import UsageReportingMixin, accumulate_usage_sink
from ...services import EmbeddingService

logger = logging.getLogger(__name__)


class AzureEmbeddingService(UsageReportingMixin, EmbeddingService, AzureBaseService):
    """
    Azure OpenAI embedding service using an embedding deployment (e.g.
    text-embedding-3-small/large). Mirrors OpenAIEmbeddingService's request
    handling — Azure exposes the same Embeddings API through the OpenAI SDK,
    just addressed by deployment name (self.model/self.deployment, set by
    AzureBaseService) instead of a raw model id.
    """

    def __init__(self, config: dict[str, Any]):
        # Only AzureBaseService.__init__ is called (not EmbeddingService's) —
        # AzureBaseService's cooperative super().__init__() already reaches
        # ProviderAIService.__init__ with ServiceType.EMBEDDING, and
        # EmbeddingService.__init__ does nothing else but set
        # dimensions/batch_size, which we set explicitly below anyway.
        # Calling both would run AzureBaseService._setup_azure_config() a
        # second time (EmbeddingService.__init__'s super().__init__() call
        # resolves to AzureBaseService.__init__ in this MRO), constructing
        # and leaking a second AsyncOpenAI client.
        AzureBaseService.__init__(self, config, ServiceType.EMBEDDING, "azure")

        self.dimensions = self._get_dimensions_config() or 1536
        self.batch_size = self._get_batch_size(default=10)

        # Azure deployment names are user-defined (e.g. "embed-prod") and
        # can't be reliably sniffed for the base model, unlike OpenAI's own
        # model ids. model_family should be configured explicitly when the
        # deployment name doesn't already contain "text-embedding-3" — only
        # that family accepts the `dimensions` request parameter; other
        # embedding models (e.g. ada-002) reject it.
        provider_config = self._extract_provider_config()
        model_family = provider_config.get("model_family")
        if not model_family:
            deployment_lower = (self.deployment or "").lower()
            if "text-embedding-3" in deployment_lower:
                model_family = "text-embedding-3"
        self.model_family = model_family
        self.supports_dimensions = self.model_family == "text-embedding-3"

    async def initialize(self) -> bool:
        """
        Initialize without AzureBaseService's inherited chat-completion probe
        (verify_connection() sends a chat.completions.create call against
        self.deployment) — an embedding-only Azure deployment rejects that
        request, which would make initialize() report failure and every
        embed_query/embed_documents call raise via _ensure_initialized even
        though the embeddings endpoint itself works fine. Only client
        construction (done in AzureBaseService.__init__) is required.
        """
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        return self.initialized

    async def embed_query(self, text: str, usage_sink=None) -> list[float]:
        """Generate embeddings for a single query text."""
        await self._ensure_initialized("Azure embedding service")

        try:
            response = await self.client.embeddings.create(
                model=self.deployment,
                input=text,
                dimensions=self.dimensions if self.supports_dimensions else None
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink, self._embedding_prompt_tokens(usage), 0
                )

            return response.data[0].embedding

        except Exception as e:
            self._handle_azure_error(e, "embedding query")
            raise

    async def embed_documents(self, texts: list[str], usage_sink=None) -> list[list[float]]:
        """Generate embeddings for multiple documents, batched to avoid rate limits."""
        await self._ensure_initialized("Azure embedding service")

        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                batch_usage = {}
                batch_embeddings = await self._embed_batch(batch_texts, usage_sink=batch_usage)
                all_embeddings.extend(batch_embeddings)
                accumulate_usage_sink(usage_sink, batch_usage)

                if i + self.batch_size < len(texts):
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                raise

        return all_embeddings

    async def _embed_batch(self, texts: list[str], usage_sink=None) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        try:
            response = await self.client.embeddings.create(
                model=self.deployment,
                input=texts,
                dimensions=self.dimensions if self.supports_dimensions else None
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink, self._embedding_prompt_tokens(usage), 0
                )

            # Sort by index to ensure order matches input order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        except Exception as e:
            self._handle_azure_error(e, "batch embedding")
            raise

    async def get_dimensions(self) -> int:
        """Get the dimensionality of the embeddings."""
        # text-embedding-3-large is 3072 dimensions; all others default to 1536
        fallback = 3072 if (self.deployment and "3-large" in self.deployment) else 1536
        return await self._resolve_dimensions(fallback)
