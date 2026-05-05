"""
xAI (Grok) image generation service using the xAI SDK.
"""

import base64
from typing import Dict, Any
from urllib.parse import urlparse

from ...connection import RetryHandler
from ...services import ImageGenerationService


class XAIImageService(ImageGenerationService):
    """xAI image generation via the official xAI SDK."""

    DEFAULT_API_BASE = "https://api.x.ai/v1"
    DEFAULT_IMAGE_MODEL = "grok-imagine-image"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "xai")
        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("XAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "xAI API key is required. Set XAI_API_KEY environment variable or provide in configuration."
            )

        self.base_url = provider_config.get("api_base") or provider_config.get("base_url") or self.DEFAULT_API_BASE
        self.model = provider_config.get("model", self.DEFAULT_IMAGE_MODEL)
        self.n = provider_config.get("n", 1)
        self.aspect_ratio = provider_config.get("aspect_ratio")
        self.resolution = provider_config.get("resolution")

        timeout_config = self._get_timeout_config()
        self._timeout_seconds = timeout_config["total"] / 1000
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
            from xai_sdk import AsyncClient

            api_host = self._normalize_api_host(self.base_url)
            self.client = AsyncClient(
                api_key=self.api_key,
                api_host=api_host,
                timeout=self._timeout_seconds,
            )
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize xAI image generation service: {e}")
            return False

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.initialized:
            if not await self.initialize():
                return False

        try:
            await self.client.models.list_image_generation_models()
            return True
        except Exception as e:
            self.logger.error(f"xAI image generation connection verification failed: {e}")
            return False

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize xAI image generation service")

        self._validate_model()

        async def _generate() -> Dict[str, Any]:
            image_format = "base64"
            n = kwargs.get("n", self.n)
            aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
            resolution = kwargs.get("resolution", self.resolution)
            user = kwargs.get("user")

            if n and int(n) > 1:
                responses = await self.client.image.sample_batch(
                    prompt=prompt,
                    model=self.model,
                    n=int(n),
                    user=user,
                    image_format=image_format,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )
                response = responses[0]
            else:
                response = await self.client.image.sample(
                    prompt=prompt,
                    model=self.model,
                    user=user,
                    image_format=image_format,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                )

            image_b64 = response.base64
            image_bytes = self._decode_data_uri(image_b64)
            image_format_name = self._infer_format(image_b64)

            return {
                "image_bytes": image_bytes,
                "format": image_format_name,
                "revised_prompt": None,
            }

        return await self.retry_handler.execute_with_retry(
            _generate,
            error_message="xAI image generation failed",
        )

    def _validate_model(self) -> None:
        if not self.model:
            raise ValueError("xAI image generation model is not configured.")

        model_lower = self.model.lower()
        if not model_lower.startswith("grok-imagine-image"):
            raise ValueError(
                "xAI image generation requires an image model such as "
                "'grok-imagine-image' or 'grok-imagine-image-pro'. "
                f"Configured model '{self.model}' is not compatible with the image endpoint."
            )

    def _normalize_api_host(self, base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.netloc:
            return parsed.netloc
        return base_url.replace("https://", "").replace("http://", "").split("/", 1)[0]

    def _decode_data_uri(self, value: str) -> bytes:
        if value.startswith("data:") and "base64," in value:
            _, encoded = value.split("base64,", 1)
            return base64.b64decode(encoded)
        return base64.b64decode(value)

    def _infer_format(self, value: str) -> str:
        if value.startswith("data:image/"):
            prefix = value.split(";", 1)[0]
            return prefix.split("/", 1)[1]
        return "png"
