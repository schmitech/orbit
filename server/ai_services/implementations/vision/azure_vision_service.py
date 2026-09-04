"""
Azure OpenAI Foundry vision service implementation.

Supports any Azure deployment reachable through chat.completions with
image_url content parts — Azure's own GPT-4o/GPT-5 vision deployments as
well as third-party vision/OCR models hosted in the Foundry Model Catalog
(e.g. Mistral OCR deployments).
"""

from typing import Any, Optional, Union
from PIL import Image

from ...base import ServiceType
from ...providers import AzureBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import VisionService


class AzureVisionService(UsageReportingMixin, VisionService, AzureBaseService):
    """
    Azure vision service using a chat-completions-capable deployment.
    Mirrors OpenAIVisionService's request handling — Azure exposes the same
    chat.completions image_url content format through the OpenAI SDK, just
    addressed by deployment name (self.model/self.deployment, set by
    AzureBaseService) instead of a raw model id.
    """

    def __init__(self, config: dict[str, Any]):
        # Only AzureBaseService.__init__ is called (not VisionService's) —
        # AzureBaseService's cooperative super().__init__() already reaches
        # ProviderAIService.__init__ with ServiceType.VISION, and
        # VisionService.__init__ does nothing else. Calling both would run
        # AzureBaseService._setup_azure_config() a second time (see the same
        # fix applied to AzureOpenAIInferenceService/AzureEmbeddingService),
        # constructing and leaking a second AsyncOpenAI client.
        AzureBaseService.__init__(self, config, ServiceType.VISION, "azure")

        self.temperature = self._get_temperature(default=0.0)
        self.max_tokens = self._get_max_tokens(default=1000)

    def _get_token_parameter_name(self) -> str:
        """
        Return the correct token-count parameter name for the active
        deployment. Azure deployment names are user-defined and can't be
        reliably sniffed like OpenAI's own model ids (e.g. a Foundry Model
        Catalog deployment such as "mistral-ocr-4-0" uses the legacy
        max_tokens parameter, not max_completion_tokens), so this defaults
        to the legacy name unless explicitly configured or the deployment
        name itself signals a modern GPT-4o/GPT-5/o-series model.
        """
        provider_config = self._extract_provider_config()

        configured_name = provider_config.get("token_parameter_name") or provider_config.get("token_parameter")
        if isinstance(configured_name, str):
            configured_name = configured_name.strip()
            if configured_name:
                return configured_name

        deployment_name = (self.deployment or "").lower()
        modern_prefixes = ("gpt-4.1", "gpt-4o", "gpt-5", "o1", "o2", "o3")
        if deployment_name.startswith(modern_prefixes):
            return "max_completion_tokens"

        return "max_tokens"

    def _resolve_token_value(self, token_param: str, kwargs: dict[str, Any]) -> int:
        """Determine the token limit value while respecting caller overrides, and
        strip every token-parameter variant out of kwargs so callers passing
        e.g. max_completion_tokens never collide with the key set below."""
        overrides = {
            "max_tokens": kwargs.pop("max_tokens", None),
            "max_completion_tokens": kwargs.pop("max_completion_tokens", None),
            "max_output_tokens": kwargs.pop("max_output_tokens", None),
        }

        param_override = overrides.get(token_param)
        if param_override is not None:
            return param_override

        for value in overrides.values():
            if value is not None:
                return value

        return self.max_tokens

    def _supports_temperature(self) -> bool:
        """
        Return whether the active deployment accepts a non-default
        temperature. Newer reasoning-style models (GPT-5/o-series, and
        third-party Foundry Catalog deployments like GPT-5.6 Luna) reject
        any temperature other than their default (1.0) with an
        unsupported_value error — mirrors the token-parameter sniffing
        above: explicit config wins, deployment-name prefix is a
        best-effort fallback since Azure deployment names are user-defined.
        """
        provider_config = self._extract_provider_config()

        configured = provider_config.get("supports_temperature")
        if isinstance(configured, bool):
            return configured

        deployment_name = (self.deployment or "").lower()
        unsupported_prefixes = ("gpt-5", "o1", "o2", "o3")
        return not deployment_name.startswith(unsupported_prefixes)

    async def verify_connection(self) -> bool:
        """
        Verify Azure connection with a minimal chat completion — overrides
        AzureBaseService.verify_connection(), which unconditionally sends
        temperature=0 and max_completion_tokens. Both are guarded here the
        same way analyze_image/multimodal_inference are, or a temperature-
        restricted deployment (e.g. gpt-5.6-luna) rejects this health check
        before initialize() ever gets a chance to call the guarded methods.
        """
        try:
            token_param = self._get_token_parameter_name()
            params = {
                "model": self.deployment,
                "messages": [{"role": "user", "content": "test"}],
                token_param: 16,
            }
            if self._supports_temperature():
                params["temperature"] = 0

            response = await self.client.chat.completions.create(**params)

            if not response.choices:
                return False
            return True
        except Exception:
            return False

    async def analyze_image(
        self,
        image: Union[str, bytes, Image.Image],
        prompt: str = "Analyze this image in detail. Describe what you see, including any text, objects, and overall context.",
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> str:
        """Analyze image content with detailed response."""
        if not self.initialized:
            await self.initialize()

        try:
            image_base64 = self._image_to_base64(image)

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ],
                }
            ]

            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, {})

            params = {
                "model": self.deployment,
                "messages": messages,
                token_param: token_value,
            }
            if self._supports_temperature():
                params["temperature"] = self.temperature

            response = await self.client.chat.completions.create(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    reasoning_tokens=self._extract_reasoning_tokens(usage),
                )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_azure_error(e, "image analysis")
            raise

    async def describe_image(
        self,
        image: Union[str, bytes, Image.Image],
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate description of image."""
        return await self.analyze_image(
            image,
            prompt="Describe this image in detail. Include the main subjects, setting, colors, and any notable features.",
            usage_sink=usage_sink,
        )

    async def extract_text_from_image(
        self,
        image: Union[str, bytes, Image.Image],
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> str:
        """Extract text from image using OCR."""
        return await self.analyze_image(
            image,
            prompt="Extract all text from this image. Return only the text content, preserving line breaks and structure.",
            usage_sink=usage_sink,
        )

    async def detect_objects(
        self,
        image: Union[str, bytes, Image.Image],
        usage_sink: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Detect objects in image (inferred from a descriptive prompt — no structured detection API)."""
        description = await self.analyze_image(
            image,
            prompt="List all objects, people, and items visible in this image. For each item, describe what it is and where it appears in the image.",
            usage_sink=usage_sink,
        )

        objects = []
        for i, line in enumerate(description.split('\n')):
            if line.strip():
                objects.append({
                    'label': line.strip(),
                    'confidence': 0.8,  # Placeholder — Azure/OpenAI-style chat vision doesn't provide explicit confidence
                    'bbox': [0, 0, 0, 0],  # Placeholder
                    'index': i
                })

        return objects

    async def multimodal_inference(
        self,
        image: Union[str, bytes, Image.Image],
        text_prompt: str,
        usage_sink: Optional[dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Perform multimodal inference with image and text."""
        if not self.initialized:
            await self.initialize()

        try:
            image_base64 = self._image_to_base64(image)

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ],
                }
            ]

            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            params = {
                "model": self.deployment,
                "messages": messages,
                token_param: token_value,
            }
            temperature_override = kwargs.pop('temperature', None)
            if self._supports_temperature():
                params["temperature"] = temperature_override if temperature_override is not None else self.temperature
            params.update(kwargs)

            response = await self.client.chat.completions.create(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    reasoning_tokens=self._extract_reasoning_tokens(usage),
                )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_azure_error(e, "multimodal inference")
            raise
