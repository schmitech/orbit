"""
Google Gemini video generation service (Veo 2).

Uses the google-genai SDK with polling to wait for the async operation to complete.
Requires the Veo 2 model which is available via Google AI Studio API key.
"""

import asyncio
import os
import time
from typing import Dict, Any

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import VideoGenerationService


class GeminiVideoService(VideoGenerationService, GoogleBaseService):
    """
    Google Veo 2 video generation service.

    Requires: pip install google-genai
    Supported models: veo-2.0-generate-001
    """

    def __init__(self, config: Dict[str, Any]):
        GoogleBaseService.__init__(self, config, ServiceType.VIDEO_GENERATION, "gemini")
        provider_config = self._extract_provider_config()
        self.aspect_ratio = provider_config.get("aspect_ratio", "16:9")
        self.number_of_videos = provider_config.get("number_of_videos", 1)
        self.person_generation = provider_config.get("person_generation", "allow_adult")
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

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a video using Google Veo 2."""
        if not self.initialized:
            await self.initialize()

        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        number_of_videos = kwargs.get("number_of_videos", self.number_of_videos)
        person_generation = kwargs.get("person_generation", self.person_generation)

        def _run_sync() -> bytes:
            from google.genai import types as genai_types

            client = self._get_client()

            operation = client.models.generate_videos(
                model=self.model,
                prompt=prompt,
                config=genai_types.GenerateVideoConfig(
                    aspect_ratio=aspect_ratio,
                    number_of_videos=number_of_videos,
                    person_generation=person_generation,
                ),
            )

            while not operation.done:
                time.sleep(5)
                operation = client.operations.get(operation)

            generated = operation.response.generated_videos
            if not generated:
                raise ValueError("Gemini Veo returned no videos")

            return client.files.download(file=generated[0].video)

        try:
            video_bytes = await asyncio.to_thread(_run_sync)
            return {
                "video_bytes": video_bytes,
                "format": "mp4",
                "duration": None,
                "revised_prompt": None,
            }
        except Exception as e:
            self.logger.error(f"Gemini video generation failed: {e}")
            raise
