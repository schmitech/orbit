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

    Always requests b64_json response format so images are returned as bytes
    with no URL expiry — safe for self-hosted deployments.
    """

    def __init__(self, config: Dict[str, Any]):
        OpenAIBaseService.__init__(self, config, ServiceType.IMAGE_GENERATION, "openai")
        provider_config = self._extract_provider_config()
        self.size = provider_config.get("size", "1024x1024")
        self.quality = provider_config.get("quality", "standard")
        self.style = provider_config.get("style", "vivid")

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image using the OpenAI Images API."""
        if not self.initialized:
            await self.initialize()

        size = kwargs.get("size", self.size)
        quality = kwargs.get("quality", self.quality)
        style = kwargs.get("style", self.style)

        params: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
            "size": size,
        }

        # quality and style are only supported by dall-e-3 and gpt-image-1
        model_lower = (self.model or "").lower()
        if "dall-e-3" in model_lower or "gpt-image" in model_lower:
            params["quality"] = quality
            if "dall-e-3" in model_lower:
                params["style"] = style

        try:
            response = await self.client.images.generate(**params)
            image_data = response.data[0]
            image_bytes = base64.b64decode(image_data.b64_json)
            revised_prompt = getattr(image_data, "revised_prompt", None)
            return {
                "image_bytes": image_bytes,
                "format": "png",
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
