"""
NVIDIA embedding service implementation using the OpenAI-compatible API.
"""

import logging
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI

from ...services import EmbeddingService


logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaEmbeddingService(EmbeddingService):
    """NVIDIA embedding service using the OpenAI-compatible NIM API."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "nvidia")

        self.dimensions = self._get_dimensions_config()
        self.batch_size = self._get_batch_size(default=10)

        self.api_key = self._resolve_api_key("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError(
                "NVIDIA API key is required. "
                "Set NVIDIA_API_KEY environment variable or provide in configuration."
            )

        self.model = self._get_model()
        if not self.model:
            raise ValueError("NVIDIA embedding model must be specified in configuration.")

        provider_config = self._extract_provider_config()
        self.truncate = provider_config.get("truncate", "NONE")

        self.client: Optional[AsyncOpenAI] = None
        logger.debug(f"Configured NVIDIA embedding service with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            if self.initialized:
                return True

            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=NVIDIA_BASE_URL,
            )

            self.initialized = True
            logger.debug(f"Initialized NVIDIA embedding service with model {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize NVIDIA embedding service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        try:
            if not self.client:
                logger.error("NVIDIA client is not initialized.")
                return False

            response = await self.client.embeddings.create(
                input="test",
                model=self.model,
                encoding_format="float",
                extra_body={"input_type": "query", "truncate": self.truncate},
            )

            if response and response.data:
                logger.debug("NVIDIA embedding connection verified successfully")
                return True

            return False

        except Exception as e:
            logger.error(f"NVIDIA embedding connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None

        self.initialized = False
        logger.debug("Closed NVIDIA embedding service")

    async def embed_query(self, text: str) -> List[float]:
        await self._ensure_initialized("NVIDIA embedding service")

        try:
            response = await self.client.embeddings.create(
                input=text,
                model=self.model,
                encoding_format="float",
                extra_body={"input_type": "query", "truncate": self.truncate},
            )
            return response.data[0].embedding

        except Exception as e:
            logger.error(f"NVIDIA embedding error: {str(e)}")
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        await self._ensure_initialized("NVIDIA embedding service")

        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]

            try:
                response = await self.client.embeddings.create(
                    input=batch_texts,
                    model=self.model,
                    encoding_format="float",
                    extra_body={"input_type": "passage", "truncate": self.truncate},
                )

                sorted_data = sorted(response.data, key=lambda x: x.index)
                all_embeddings.extend(item.embedding for item in sorted_data)

            except Exception as e:
                logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                raise

        return all_embeddings

    async def get_dimensions(self) -> int:
        return await self._resolve_dimensions(4096)
