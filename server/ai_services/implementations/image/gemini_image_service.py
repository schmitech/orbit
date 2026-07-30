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

    def _is_gemini_model(self) -> bool:
        return self.model.startswith("gemini-")

    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate an image using Google Gemini or Imagen."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.genai import types as genai_types

            client = self._get_client()

            usage_dict = None
            media_usage = None
            if self._is_gemini_model():
                # Gemini models (e.g. gemini-3.1-flash-image) use generate_content
                # with IMAGE response modality, not the Imagen generate_images API.
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )
                image_bytes = None
                for part in (response.parts or []):
                    if part.inline_data is not None:
                        image_bytes = part.inline_data.data
                        break
                if image_bytes is None:
                    raise ValueError("Gemini returned no image data")

                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
                    completion_tokens = getattr(usage, "candidates_token_count", None) or 0
                    usage_dict = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                        "provider": self.provider_name,
                        "model": self.model,
                        "reported": True,
                    }
            else:
                # Imagen models use the generate_images API — billed per image,
                # not per token (see Phase 4 / pricing.media), no usage_metadata.
                aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
                number_of_images = kwargs.get("number_of_images", self.number_of_images)
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
                media_usage = {"unit": "images", "quantity": len(response.generated_images)}

            return {
                "image_bytes": image_bytes,
                "format": "png",
                "revised_prompt": None,
                "usage": usage_dict,
                "media_usage": media_usage,
            }
        except Exception as e:
            self.logger.error(f"Gemini image generation failed: {e}")
            raise
