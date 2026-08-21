"""
OpenRouter video generation service using the native OpenRouter SDK.

Video generation is asynchronous: a job is submitted, then polled until it
completes, matching the flow described at
https://openrouter.ai/docs/api/api-reference/video-generation/submit-a-video-generation-request
"""

import asyncio
import logging
import time
from typing import Dict, Any

from openrouter import OpenRouter
from openrouter.utils.retries import BackoffStrategy, RetryConfig

from ...connection import RetryHandler
from ...services import VideoGenerationService


logger = logging.getLogger(__name__)

# RetryHandler already governs retries/backoff; disable the SDK's own retry
# loop so a single execute_with_retry attempt maps to a single HTTP request.
_NO_SDK_RETRIES = RetryConfig(
    strategy="none",
    backoff=BackoffStrategy(initial_interval=1, max_interval=1, exponent=1.0, max_elapsed_time=1),
    retry_connection_errors=False,
)

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "expired"}
_POLL_INTERVAL_SECONDS = 5


class OpenRouterVideoService(VideoGenerationService):
    """OpenRouter video generation service using the native OpenRouter SDK."""

    DEFAULT_VIDEO_MODEL = "google/veo-3.1"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "openrouter")
        provider_config = self._extract_provider_config()

        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide in configuration."
            )

        self.model = provider_config.get("model", self.DEFAULT_VIDEO_MODEL)
        self.aspect_ratio = provider_config.get("aspect_ratio", "16:9")
        self.resolution = provider_config.get("resolution")
        self.duration = provider_config.get("duration")

        timeout_config = self._get_timeout_config()
        self._timeout_ms = timeout_config["total"]
        self._timeout_seconds = self._timeout_ms / 1000

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
            self.client = OpenRouter(
                api_key=self.api_key,
                timeout_ms=self._timeout_ms,
                retry_config=_NO_SDK_RETRIES,
            )
            self.initialized = True
            logger.debug(f"Initialized OpenRouter video generation service with model {self.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter video generation service: {e}")
            return False

    async def close(self) -> None:
        self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.initialized:
            if not await self.initialize():
                return False

        try:
            await self.client.video_generation.list_videos_models_async()
            return True
        except Exception as e:
            logger.error(f"OpenRouter video generation connection verification failed: {e}")
            return False

    async def generate_video(self, prompt: str, **kwargs) -> Dict[str, Any]:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize OpenRouter video generation service")

        model = kwargs.get("model") or self.model
        aspect_ratio = kwargs.get("aspect_ratio", self.aspect_ratio)
        resolution = kwargs.get("resolution", self.resolution)
        duration = kwargs.get("duration", self.duration)

        deadline = time.monotonic() + self._timeout_seconds

        params = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration": duration,
        }
        params = {k: v for k, v in params.items() if v is not None}

        # Submission is NOT retried: OpenRouter may create the job before the
        # client observes a timeout/connection error, so retrying here could
        # pay for and abandon a second video. Once a job exists, only polling
        # and download (which act on that same job ID) may be retried.
        try:
            job = await asyncio.wait_for(
                self.client.video_generation.generate_async(**params),
                timeout=max(deadline - time.monotonic(), 0),
            )
        except Exception as e:
            raise ValueError(f"OpenRouter video submission failed: {e}") from e

        async def _finish() -> Dict[str, Any]:
            completed = await self._poll_until_done(job.id)

            if completed.status != "completed":
                raise ValueError(
                    f"OpenRouter video generation ended with status '{completed.status}': {completed.error}"
                )

            video_response = await self.client.video_generation.get_video_content_async(job_id=job.id, index=0)
            video_bytes = await video_response.aread()

            usage = getattr(completed, "usage", None)
            media_usage = None
            if usage is not None and duration:
                media_usage = {"unit": "seconds", "quantity": duration}

            return {
                "video_bytes": video_bytes,
                "format": "mp4",
                "duration": duration,
                "revised_prompt": None,
                "media_usage": media_usage,
            }

        # Wrap the whole retry loop (including RetryHandler's own backoff
        # sleeps) in a single deadline so retries can't sleep past the
        # configured total timeout before making an already-doomed attempt.
        return await asyncio.wait_for(
            self.retry_handler.execute_with_retry(
                _finish,
                error_message="OpenRouter video generation failed",
            ),
            timeout=max(deadline - time.monotonic(), 0),
        )

    async def _poll_until_done(self, job_id: str):
        while True:
            job = await self.client.video_generation.get_generation_async(job_id=job_id)
            if job.status in _TERMINAL_STATUSES:
                return job
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
