"""
xAI (Grok) video generation service using the xAI SDK.

Uses the xAI AsyncClient which handles async polling automatically.
The API returns a hosted URL; bytes are downloaded before returning.
"""

from datetime import timedelta
from typing import Dict, Any
from urllib.parse import urlparse

from ...connection import RetryHandler
from ...services import VideoGenerationService


class XAIVideoService(VideoGenerationService):
    """xAI video generation via the official xAI SDK."""

    DEFAULT_API_BASE = "https://api.x.ai/v1"
    DEFAULT_VIDEO_MODEL = "grok-imagine-video"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "xai")
        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("XAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "xAI API key is required. Set XAI_API_KEY environment variable or provide in configuration."
            )

        self.base_url = provider_config.get("api_base") or provider_config.get("base_url") or self.DEFAULT_API_BASE
        self.model = provider_config.get("model", self.DEFAULT_VIDEO_MODEL)
        self.aspect_ratio = provider_config.get("aspect_ratio", "16:9")
        self.resolution = provider_config.get("resolution")
        self.duration = provider_config.get("duration", 5)

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
            )
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize xAI video generation service: {e}")
            return False

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.initialized:
            return await self.initialize()
        return True

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize xAI video generation service")

        self._validate_model()

        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        resolution = kwargs.get("resolution", self.resolution)
        duration = kwargs.get("duration", self.duration)

        async def _generate() -> Dict[str, Any]:
            from xai_sdk.video import VideoGenerationError

            try:
                response = await self.client.video.generate(
                    prompt=prompt,
                    model=self.model,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    timeout=timedelta(seconds=self._timeout_seconds),
                )
            except VideoGenerationError as e:
                raise ValueError(f"xAI video generation failed [{e.code}]: {e.message}") from e

            video_bytes = await self._download_video(response.url)

            return {
                "video_bytes": video_bytes,
                "format": "mp4",
                "duration": getattr(response, "duration", None),
                "revised_prompt": None,
            }

        return await self.retry_handler.execute_with_retry(
            _generate,
            error_message="xAI video generation failed",
        )

    async def _download_video(self, url: str) -> bytes:
        import httpx
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(url, timeout=60.0)
            resp.raise_for_status()
            return resp.content

    def _validate_model(self) -> None:
        if not self.model:
            raise ValueError("xAI video generation model is not configured.")

        if not self.model.lower().startswith("grok-imagine-video"):
            raise ValueError(
                "xAI video generation requires a video model such as 'grok-imagine-video'. "
                f"Configured model '{self.model}' is not compatible with the video endpoint."
            )

    def _normalize_api_host(self, base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.netloc:
            return parsed.netloc
        return base_url.replace("https://", "").replace("http://", "").split("/", 1)[0]
