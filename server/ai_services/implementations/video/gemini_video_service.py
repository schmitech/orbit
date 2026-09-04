"""
Google Gemini video generation service (Veo).

Uses the google-genai SDK with polling to wait for the async operation to complete.
Requires a Veo model which is available via Google AI Studio API key.
"""

import asyncio
import os
import time
from typing import Any

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import VideoGenerationService


class GeminiVideoService(VideoGenerationService, GoogleBaseService):
    """
    Google Veo video generation service.

    Requires: pip install google-genai
    Supported models: veo-3.1-generate-preview, veo-3.1-generate-001, veo-2.0-generate-001
    """

    def __init__(self, config: dict[str, Any]):
        GoogleBaseService.__init__(self, config, ServiceType.VIDEO_GENERATION, "gemini")
        provider_config = self._extract_provider_config()
        self.aspect_ratio = provider_config.get("aspect_ratio", "16:9")
        self.number_of_videos = provider_config.get("number_of_videos", 1)
        self.duration = provider_config.get("duration")
        # None (the default) omits personGeneration entirely — Veo 3.x preview models
        # reject "allow_adult" for text-to-video with a 400 INVALID_ARGUMENT; only set
        # this if your account/model combination is confirmed to accept a specific value.
        self.person_generation = provider_config.get("person_generation")
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

    async def generate_video(self, prompt: str, **kwargs) -> dict[str, Any]:
        """Generate a video using Google Veo 2."""
        if not self.initialized:
            await self.initialize()

        model = kwargs.get("model") or self.model
        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        number_of_videos = kwargs.get("number_of_videos", self.number_of_videos)
        duration = kwargs.get("duration", self.duration)
        person_generation = kwargs.get("person_generation", self.person_generation)

        def _run_sync() -> tuple[bytes, str]:
            from google.genai import types as genai_types

            client = self._get_client()

            config_kwargs = {
                "aspect_ratio": aspect_ratio,
                "number_of_videos": number_of_videos,
            }
            if duration is not None:
                config_kwargs["duration_seconds"] = duration
            if person_generation:
                config_kwargs["person_generation"] = person_generation

            operation = client.models.generate_videos(
                model=model,
                prompt=prompt,
                config=genai_types.GenerateVideosConfig(**config_kwargs),
            )

            while not operation.done:
                time.sleep(5)
                operation = client.operations.get(operation)

            generated = (operation.response or operation.result or {})
            videos = getattr(generated, 'generated_videos', None) or []
            if not videos:
                raise ValueError("Gemini Veo returned no videos")

            video_obj = videos[0].video
            video_bytes = video_obj.video_bytes
            if not video_bytes:
                # API returned a URI — download the bytes explicitly
                video_bytes = client.files.download(file=video_obj)

            mime = video_obj.mime_type or "video/mp4"
            fmt = mime.split("/")[-1] if "/" in mime else "mp4"
            return video_bytes, fmt

        try:
            video_bytes, fmt = await asyncio.to_thread(_run_sync)
            return {
                "video_bytes": video_bytes,
                "format": fmt,
                "duration": None,
                "revised_prompt": None,
            }
        except Exception as e:
            self.logger.error(f"Gemini video generation failed: {e}")
            raise
