"""
OpenAI image generation service (DALL-E 2/3, GPT-Image-1).
"""

import base64
from typing import Dict, Any

from ...base import ServiceType
from ...providers import OpenAIBaseService
from ...services import ImageGenerationService


class OpenAIImageService(ImageGenerationService, OpenAIBaseService):
    """
    OpenAI image generation using DALL-E 2/3 or GPT-Image-1.

    GPT Image models return b64_json by default. DALL-E models still need an
    explicit b64_json response_format to avoid expiring URLs.
    """

    def __init__(self, config: Dict[str, Any]):
        OpenAIBaseService.__init__(self, config, ServiceType.IMAGE_GENERATION, "openai")
        provider_config = self._extract_provider_config()
        self.size = provider_config.get("size", "1024x1024")
        self.quality = provider_config.get("quality", "auto")
        self.style = provider_config.get("style", "vivid")
        self.output_format = provider_config.get("output_format", "png")
        self.output_compression = provider_config.get("output_compression")
        self.background = provider_config.get("background")
        self.moderation = provider_config.get("moderation")

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image using the OpenAI Images API."""
        if not self.initialized:
            await self.initialize()

        size = kwargs.get("size", self.size)
        quality = kwargs.get("quality", self.quality)
        style = kwargs.get("style", self.style)
        output_format = kwargs.get("output_format", self.output_format)
        output_compression = kwargs.get("output_compression", self.output_compression)
        background = kwargs.get("background", self.background)
        moderation = kwargs.get("moderation", self.moderation)
        model_lower = (self.model or "").lower()
        is_gpt_image = model_lower.startswith("gpt-image")
        is_dalle = model_lower.startswith("dall-e")

        params: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

        if is_gpt_image:
            params["quality"] = quality
            if output_format:
                params["output_format"] = output_format
            if output_compression is not None:
                params["output_compression"] = output_compression
            if background:
                params["background"] = background
            if moderation:
                params["moderation"] = moderation
        elif is_dalle:
            params["response_format"] = "b64_json"
            if model_lower == "dall-e-3":
                params["quality"] = quality
                params["style"] = style

        try:
            response = await self.client.images.generate(**params)
            image_data = response.data[0]
            if not image_data.b64_json:
                raise ValueError("OpenAI image generation did not return b64_json image data")

            image_bytes = base64.b64decode(image_data.b64_json)
            revised_prompt = getattr(image_data, "revised_prompt", None)
            return {
                "image_bytes": image_bytes,
                "format": output_format if is_gpt_image and output_format else "png",
                "revised_prompt": revised_prompt,
            }
        except Exception as e:
            self._handle_openai_error(e, "image generation")
            raise

    async def verify_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False
