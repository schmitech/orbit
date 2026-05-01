"""
Google Gemini image generation service (Imagen 3).

Uses the google-genai SDK. Requires the Imagen 3 model which is available
via Google AI Studio API key.
"""

import asyncio
import os
from typing import Dict, Any

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import ImageGenerationService


class GeminiImageService(ImageGenerationService, GoogleBaseService):
    """
    Google Imagen 3 image generation service.

    Requires: pip install google-genai
    Supported models: imagen-3.0-generate-001, imagen-3.0-fast-generate-001
    """

    def __init__(self, config: Dict[str, Any]):
        GoogleBaseService.__init__(self, config, ServiceType.IMAGE_GENERATION, "gemini")
        provider_config = self._extract_provider_config()
        self.number_of_images = provider_config.get("number_of_images", 1)
        self.aspect_ratio = provider_config.get("aspect_ratio", "1:1")
        self._genai_client = None

    def _get_client(self):
        if self._genai_client is None:
            from google import genai
            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key
            self._genai_client = genai.Client()
        return self._genai_client

    async def initialize(self) -> bool:
        self.initialized = True
        return True

    async def close(self) -> None:
        self._genai_client = None

    async def verify_connection(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image using Google Imagen 3."""
        if not self.initialized:
            await self.initialize()

        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        number_of_images = kwargs.get("number_of_images", self.number_of_images)

        try:
            from google.genai import types as genai_types

            client = self._get_client()

            response = await asyncio.to_thread(
                client.models.generate_images,
                model=self.model,
                prompt=prompt,
                config=genai_types.GenerateImagesConfig(
                    number_of_images=number_of_images,
                    aspect_ratio=aspect_ratio,
                ),
            )

            if not response.generated_images:
                raise ValueError("Gemini returned no images")

            image_bytes = response.generated_images[0].image.image_bytes
            return {
                "image_bytes": image_bytes,
                "format": "png",
                "revised_prompt": None,
            }
        except Exception as e:
            self.logger.error(f"Gemini image generation failed: {e}")
            raise
