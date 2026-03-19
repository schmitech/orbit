"""
Ollama Cloud vision service implementation for the unified architecture.

This mirrors the local Ollama vision service while reading credentials and
settings from the dedicated `ollama_cloud` provider configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from ollama import AsyncClient
from PIL import Image

from ...connection import RetryHandler
from ...services import VisionService

logger = logging.getLogger(__name__)


class OllamaCloudVisionService(VisionService):
    """Vision service backed by the managed Ollama Cloud offering."""

    _OPTION_KEYS = (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "presence_penalty",
        "frequency_penalty",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
        "num_ctx",
        "num_keep",
        "penalize_newline",
        "num_predict",
        "seed",
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "ollama_cloud")

        provider_config = self._extract_provider_config()

        self.api_key: Optional[str] = self._resolve_api_key("OLLAMA_CLOUD_API_KEY")
        self.base_url: str = provider_config.get("base_url", "https://ollama.com")
        self.model = self._get_model("qwen3.5")

        self.temperature = provider_config.get("temperature", 0.0)
        self.max_tokens = provider_config.get("max_tokens", 1000)
        self.top_p = provider_config.get("top_p", 0.9)
        self.stream = provider_config.get("stream", False)
        self.think = provider_config.get("think", False)

        self._default_options: Dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        for key in self._OPTION_KEYS:
            value = provider_config.get(key)
            if value is not None:
                self._default_options[key] = value
        if "num_predict" not in self._default_options and self.max_tokens:
            self._default_options["num_predict"] = self.max_tokens

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config["max_retries"],
            initial_wait_ms=retry_config["initial_wait_ms"],
            max_wait_ms=retry_config["max_wait_ms"],
            exponential_base=retry_config["exponential_base"],
            enabled=retry_config["enabled"],
        )

        self.client: Optional[AsyncClient] = None

    async def initialize(self) -> bool:
        """Initialise the Ollama Cloud client and verify connectivity."""
        if self.initialized:
            return True

        if not self.api_key:
            logger.error("Ollama Cloud API key is not configured")
            return False

        try:
            self.client = AsyncClient(
                host=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

            if await self.verify_connection():
                self.initialized = True
                logger.info(
                    "Initialized Ollama Cloud vision service with model %s",
                    self.model,
                )
                return True

            logger.warning("Ollama Cloud vision connection verification failed")
            return False
        except Exception as exc:
            logger.error("Failed to initialize Ollama Cloud vision client: %s", exc)
            self.client = None
            return False

    async def close(self) -> None:
        """Release the client. AsyncClient does not expose close()."""
        self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        """Verify Ollama Cloud credentials and model access."""
        try:
            if not self.api_key:
                logger.error("Ollama Cloud API key is not configured")
                return False

            temp_client = self.client
            if temp_client is None:
                temp_client = AsyncClient(
                    host=self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )

            try:
                models = await temp_client.list()
                if models and hasattr(models, "models") and models.models:
                    logger.debug("Ollama Cloud vision connection verified successfully")
                    return True
            except Exception as list_exc:
                logger.debug("Model list failed, trying chat request: %s", list_exc)
                await temp_client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": "ping"}],
                    options={"num_predict": 1},
                )

            return True
        except Exception as exc:
            logger.error("Failed to verify Ollama Cloud vision connection: %s", exc)
            return False

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context.",
    ) -> str:
        return await self.multimodal_inference(image, prompt)

    async def describe_image(self, image: Union[str, bytes, Image.Image]) -> str:
        return await self.analyze_image(
            image,
            prompt="Describe this image in detail. Include the main subjects, setting, colors, and any notable features.",
        )

    async def extract_text_from_image(self, image: Union[str, bytes, Image.Image]) -> str:
        return await self.analyze_image(
            image,
            prompt="Extract all text from this image. Return only the text content, preserving line breaks and structure.",
        )

    async def detect_objects(self, image: Union[str, bytes, Image.Image]) -> List[Dict[str, Any]]:
        description = await self.analyze_image(
            image,
            prompt="List all objects, people, and items visible in this image. For each item, describe what it is and where it appears in the image.",
        )

        objects: List[Dict[str, Any]] = []
        for index, line in enumerate(description.splitlines()):
            if line.strip():
                objects.append(
                    {
                        "label": line.strip(),
                        "confidence": 0.8,
                        "bbox": [0, 0, 0, 0],
                        "index": index,
                    }
                )
        return objects

    async def multimodal_inference(
        self,
        image: Union[str, bytes, Image.Image],
        text_prompt: str,
        **kwargs: Any,
    ) -> str:
        if not self.initialized and not await self.initialize():
            raise ValueError("Failed to initialize Ollama Cloud vision service")

        assert self.client is not None

        async def _inference() -> str:
            options = self._build_options(kwargs)
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": text_prompt,
                        "images": [self._image_to_base64(image)],
                    }
                ],
                stream=False,
                think=kwargs.get("think", self.think),
                options=options,
            )
            return self._extract_content(response)

        return await self.retry_handler.execute_with_retry(
            _inference,
            error_message="Ollama Cloud vision request failed",
        )

    def _build_options(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        options = dict(self._default_options)
        local_overrides = dict(overrides)

        token_override = None
        for key in ("num_predict", "max_tokens", "max_completion_tokens", "max_output_tokens"):
            if key in local_overrides:
                value = local_overrides.pop(key)
                if value is not None:
                    token_override = value

        for key in self._OPTION_KEYS:
            if key in local_overrides:
                value = local_overrides.pop(key)
                if value is None:
                    options.pop(key, None)
                else:
                    options[key] = value

        if token_override is not None:
            options["num_predict"] = token_override

        return {key: value for key, value in options.items() if value is not None}

    @staticmethod
    def _extract_content(response: Any) -> str:
        if hasattr(response, "message"):
            message = response.message
            if hasattr(message, "content"):
                return message.content or ""
            if isinstance(message, dict):
                return message.get("content", "")
            return ""

        if isinstance(response, dict):
            return response.get("message", {}).get("content", "")

        if hasattr(response, "model_dump"):
            data = response.model_dump()
            return data.get("message", {}).get("content", "")

        logger.warning("Unexpected response type from Ollama Cloud vision: %s", type(response))
        return ""
