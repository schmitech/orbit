"""
Ollama image generation service implementation.

Uses Ollama's experimental OpenAI-compatible image generation endpoint.
"""

import base64
from typing import Dict, Any

from ...base import ServiceType
from ...providers import OllamaBaseService
from ...services import ImageGenerationService


class OllamaImageService(ImageGenerationService, OllamaBaseService):
    """Generate images with an Ollama image model."""

    def __init__(self, config: Dict[str, Any]):
        OllamaBaseService.__init__(self, config, ServiceType.IMAGE_GENERATION, "ollama")
        provider_config = self._extract_provider_config()
        self.size = provider_config.get("size", "1024x1024")
        self.quality = provider_config.get("quality", "standard")
        self.style = provider_config.get("style")
        self.n = provider_config.get("n", 1)

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image using Ollama's OpenAI-compatible images endpoint."""
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama image generation service")

        async def _generate():
            session = await self.session_manager.get_session()
            url = self._build_images_url()

            payload: Dict[str, Any] = {
                "model": self.model,
                "prompt": prompt,
                "n": kwargs.get("n", self.n),
                "size": kwargs.get("size", self.size),
                "response_format": "b64_json",
            }

            quality = kwargs.get("quality", self.quality)
            if quality:
                payload["quality"] = quality

            style = kwargs.get("style", self.style)
            if style:
                payload["style"] = style

            user = kwargs.get("user")
            if user:
                payload["user"] = user

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama image generation error: {error_text}")

                data = await response.json()
                items = data.get("data") or []
                if not items:
                    raise ValueError("Ollama returned no image data")

                image_data = items[0]
                b64_json = image_data.get("b64_json")
                if not b64_json:
                    raise ValueError("Ollama response did not include b64_json image data")

                return {
                    "image_bytes": base64.b64decode(b64_json),
                    "format": self._infer_format(image_data),
                    "revised_prompt": image_data.get("revised_prompt"),
                }

        return await self.execute_with_retry(_generate)

    def _build_images_url(self) -> str:
        """Translate the configured Ollama base URL into the images endpoint URL."""
        base_url = (self.base_url or "").rstrip("/")
        if base_url.endswith("/api"):
            base_url = base_url[:-4]
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return f"{base_url}/images/generations"

    def _infer_format(self, image_data: Dict[str, Any]) -> str:
        """Infer the returned image format with a safe default."""
        mime_type = image_data.get("mime_type") or image_data.get("content_type") or ""
        if "/" in mime_type:
            return mime_type.split("/", 1)[1]
        return "png"
