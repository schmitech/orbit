"""OpenRouter vision service using the native OpenRouter SDK."""

import base64
from typing import Any

from openrouter import OpenRouter
from openrouter.utils.retries import BackoffStrategy, RetryConfig
from PIL import Image

from ...connection import RetryHandler
from ...errors import raise_sanitized
from ...providers.usage_reporting import UsageReportingMixin
from ...services import VisionService

# RetryHandler owns retries so each SDK call makes one HTTP attempt.
_NO_SDK_RETRIES = RetryConfig(
    strategy="none",
    backoff=BackoffStrategy(initial_interval=1, max_interval=1, exponent=1.0, max_elapsed_time=1),
    retry_connection_errors=False,
)


class OpenRouterVisionService(UsageReportingMixin, VisionService):
    """Image analysis, OCR, and multimodal prompts through OpenRouter."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "openrouter")
        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key is required for vision")

        provider_config = self._extract_provider_config()
        self.model = self._get_model("openai/gpt-4o")
        self.temperature = provider_config.get("temperature", 0.0)
        self.max_tokens = provider_config.get("max_tokens", 1000)
        self._timeout_ms = self._get_timeout_config()["total"]
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )
        self.client: OpenRouter | None = None

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
            return True
        except Exception as exc:  # noqa: BLE001 - provider boundary
            self.logger.error("Failed to initialize OpenRouter vision service: %s", exc)
            return False

    async def close(self) -> None:
        if self.client is not None:
            async_client = self.client.sdk_configuration.async_client
            if async_client is not None and not self.client.sdk_configuration.async_client_supplied:
                await async_client.aclose()
            self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        if not self.initialized and not await self.initialize():
            return False
        try:
            response = await self.client.chat.send_async(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return bool(response.choices)
        except Exception as exc:  # noqa: BLE001 - provider boundary
            self.logger.error("OpenRouter vision connection verification failed: %s", exc)
            return False

    async def analyze_image(
        self,
        image: str | bytes | Image.Image,
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context.",
        usage_sink: dict[str, Any] | None = None,
    ) -> str:
        return await self.multimodal_inference(image, prompt, usage_sink=usage_sink)

    async def describe_image(
        self, image: str | bytes | Image.Image, usage_sink: dict[str, Any] | None = None,
    ) -> str:
        return await self.analyze_image(
            image,
            "Describe this image in detail. Include the main subjects, setting, colors, and notable features.",
            usage_sink=usage_sink,
        )

    async def extract_text_from_image(
        self, image: str | bytes | Image.Image, usage_sink: dict[str, Any] | None = None,
    ) -> str:
        return await self.analyze_image(
            image,
            "Extract all text from this image. Return only the text, preserving line breaks and structure.",
            usage_sink=usage_sink,
        )

    async def detect_objects(
        self, image: str | bytes | Image.Image, usage_sink: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        description = await self.analyze_image(
            image,
            "List all objects, people, and items visible in this image, one per line.",
            usage_sink=usage_sink,
        )
        return [
            {"label": line.strip(), "confidence": 0.8, "bbox": [0, 0, 0, 0], "index": index}
            for index, line in enumerate(description.splitlines()) if line.strip()
        ]

    async def multimodal_inference(
        self,
        image: str | bytes | Image.Image,
        text_prompt: str,
        usage_sink: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        if not self.initialized and not await self.initialize():
            raise ValueError("Failed to initialize OpenRouter vision service")

        # Preserve the input's actual media type; JPEG, GIF, and WebP must not
        # be labeled as PNG in the data URL.
        mime_type = self._get_image_mime_type(image)
        image_data = base64.b64encode(self._prepare_image(image)).decode("ascii")
        params = {
            "model": kwargs.pop("model", self.model),
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
                ],
            }],
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "temperature": kwargs.pop("temperature", self.temperature),
        }
        params.update(kwargs)

        async def _send() -> str:
            response = await self.client.chat.send_async(**params)
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    reasoning_tokens=self._extract_reasoning_tokens(usage),
                )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("OpenRouter returned no vision content")
            return response.choices[0].message.content

        try:
            return await self.retry_handler.execute_with_retry(_send, error_message="OpenRouter vision failed")
        except Exception as exc:  # noqa: BLE001 - provider boundary
            raise_sanitized(exc, provider="openrouter", operation="vision analysis")
