"""
OpenRouter image generation service using the native OpenRouter SDK.

API Documentation: https://openrouter.ai/docs/api/api-reference/images/generate-an-image
"""

import base64
import logging
from typing import Dict, Any

from openrouter import OpenRouter
from openrouter.utils.retries import BackoffStrategy, RetryConfig

from ...connection import RetryHandler
from ...services import ImageGenerationService

# RetryHandler already governs retries/backoff; disable the SDK's own retry
# loop so a single execute_with_retry attempt maps to a single HTTP request.
_NO_SDK_RETRIES = RetryConfig(
    strategy="none",
    backoff=BackoffStrategy(initial_interval=1, max_interval=1, exponent=1.0, max_elapsed_time=1),
    retry_connection_errors=False,
)


logger = logging.getLogger(__name__)


class OpenRouterImageService(ImageGenerationService):
    """OpenRouter image generation service using the native OpenRouter SDK."""

    DEFAULT_IMAGE_MODEL = "bytedance-seed/seedream-4.5"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "openrouter")
        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide in configuration."
            )

        self.model = provider_config.get("model", self.DEFAULT_IMAGE_MODEL)
        self.size = provider_config.get("size")
        self.aspect_ratio = provider_config.get("aspect_ratio")
        self.quality = provider_config.get("quality")

        timeout_config = self._get_timeout_config()
        self._timeout_ms = timeout_config["total"]

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )
        self.client = None

    async def initialize(self) -> bool:
        if self.initialized:
            return True

        try:
            self.client = OpenRouter(
                api_key=self.api_key,
                timeout_ms=self._timeout_ms,
                retry_config=_NO_SDK_RETRIES,
            )
            self.initialized = True
            logger.debug(f"Initialized OpenRouter image generation service with model {self.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter image generation service: {e}")
            return False

    async def close(self) -> None:
        self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.initialized:
            if not await self.initialize():
                return False

        try:
            await self.client.images.list_models_async()
            return True
        except Exception as e:
            logger.error(f"OpenRouter image generation connection verification failed: {e}")
            return False

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize OpenRouter image generation service")

        model = kwargs.get("model") or self.model

        async def _generate() -> Dict[str, Any]:
            params = {
                "model": model,
                "prompt": prompt,
                "n": 1,  # generate_image() returns a single image; don't pay for discarded ones
                "size": kwargs.get("size", self.size),
                "aspect_ratio": kwargs.get("aspect_ratio", self.aspect_ratio),
                "quality": kwargs.get("quality", self.quality),
            }
            params = {k: v for k, v in params.items() if v is not None}

            response = await self.client.images.generate_async(**params)

            if not response.data:
                raise ValueError("OpenRouter returned no image data")

            image_data = response.data[0]
            image_bytes = base64.b64decode(image_data.b64_json)
            image_format = "png"
            media_type = getattr(image_data, "media_type", None)
            if media_type and "/" in media_type:
                image_format = media_type.split("/", 1)[1]

            usage_dict = None
            usage = getattr(response, "usage", None)
            if usage is not None:
                usage_dict = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                    "provider": self.provider_name,
                    "model": model,
                    "reported": True,
                }

            return {
                "image_bytes": image_bytes,
                "format": image_format,
                "revised_prompt": None,
                "usage": usage_dict,
            }

        return await self.retry_handler.execute_with_retry(
            _generate,
            error_message="OpenRouter image generation failed",
        )
