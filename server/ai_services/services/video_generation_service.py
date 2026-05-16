"""
Video generation service interface.

Defines the common interface for all video generation services,
providing a unified API regardless of the underlying provider (Gemini, etc.).
"""

from abc import abstractmethod
from typing import Dict, Any, Optional

from ..base import ProviderAIService, ServiceType


class VideoGenerationService(ProviderAIService):
    """
    Base class for all video generation services.

    Implementations must return a dict from generate_video() with:
        video_bytes: bytes          — raw video data
        format: str                 — "mp4"
        duration: float | None      — duration in seconds, if known
        revised_prompt: str | None  — provider-rewritten prompt
    """

    service_type = ServiceType.VIDEO_GENERATION

    def __init__(self, config: Dict[str, Any], provider_name: str):
        super().__init__(config, ServiceType.VIDEO_GENERATION, provider_name)

    @abstractmethod
    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate a video from a text prompt.

        Args:
            prompt: Text description of the video to generate
            **kwargs: Provider-specific overrides (aspect_ratio, duration, etc.)

        Returns:
            {
                "video_bytes": bytes,
                "format": str,                # "mp4"
                "duration": float | None,
                "revised_prompt": str | None,
            }
        """
        pass
