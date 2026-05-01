"""
Image generation service interface.

Defines the common interface for all image generation services,
providing a unified API regardless of the underlying provider (OpenAI, Gemini, etc.).
"""

from abc import abstractmethod
from typing import Dict, Any, Optional

from ..base import ProviderAIService, ServiceType


class ImageGenerationService(ProviderAIService):
    """
    Base class for all image generation services.

    Implementations must return a dict from generate_image() with:
        image_bytes: bytes          — raw image data
        format: str                 — "png", "jpeg", or "webp"
        revised_prompt: str | None  — provider-rewritten prompt (e.g. DALL-E 3)
    """

    service_type = ServiceType.IMAGE_GENERATION

    def __init__(self, config: Dict[str, Any], provider_name: str):
        super().__init__(config, ServiceType.IMAGE_GENERATION, provider_name)

    @abstractmethod
    async def generate_image(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Text description of the image to generate
            **kwargs: Provider-specific overrides (size, quality, style, etc.)

        Returns:
            {
                "image_bytes": bytes,
                "format": str,           # "png", "jpeg", or "webp"
                "revised_prompt": str | None,
            }
        """
        pass
