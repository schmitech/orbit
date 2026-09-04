"""
Azure OpenAI image generation service (GPT-Image-1, DALL-E 2/3 deployments).
"""

import base64
from typing import Any

from ...base import ServiceType
from ...providers import AzureBaseService
from ...services import ImageGenerationService


class AzureImageService(ImageGenerationService, AzureBaseService):
    """
    Azure OpenAI Foundry image generation using a GPT-Image or DALL-E
    deployment. Mirrors OpenAIImageService's request/response handling —
    Azure exposes the same Images API through the OpenAI SDK, just addressed
    by deployment name (self.model/self.deployment, set by AzureBaseService)
    instead of a raw model id.
    """

    def __init__(self, config: dict[str, Any]):
        AzureBaseService.__init__(self, config, ServiceType.IMAGE_GENERATION, "azure")
        provider_config = self._extract_provider_config()
        self.size = provider_config.get("size", "1024x1024")
        self.quality = provider_config.get("quality", "auto")
        self.style = provider_config.get("style", "vivid")
        self.output_format = provider_config.get("output_format", "png")
        self.output_compression = provider_config.get("output_compression")
        self.background = provider_config.get("background")
        self.moderation = provider_config.get("moderation")
        # Azure deployment names are user-defined (e.g. "image-prod") and
        # can't be reliably sniffed for family, unlike OpenAI's own model
        # ids. model_family must be configured explicitly: "gpt-image" or
        # "dall-e". Falls back to sniffing the deployment name only as a
        # convenience for the common case of naming a deployment after its
        # base model.
        model_family = provider_config.get("model_family")
        if not model_family:
            deployment_lower = (self.deployment or "").lower()
            if "gpt-image" in deployment_lower:
                model_family = "gpt-image"
            elif "dall-e" in deployment_lower or "dalle" in deployment_lower:
                model_family = "dall-e"
        self.model_family = model_family
        # Only relevant when model_family == "dall-e"; same naming ambiguity
        # means this must also be explicit, defaulting to the newer version.
        self.dalle_version = provider_config.get("dalle_version", "dall-e-3")

    async def generate_image(self, prompt: str, **kwargs) -> dict[str, Any]:
        """Generate an image using the Azure OpenAI Images API."""
        if not self.initialized:
            await self.initialize()

        deployment = kwargs.get("model") or self.deployment
        size = kwargs.get("size", self.size)
        quality = kwargs.get("quality", self.quality)
        style = kwargs.get("style", self.style)
        output_format = kwargs.get("output_format", self.output_format)
        output_compression = kwargs.get("output_compression", self.output_compression)
        background = kwargs.get("background", self.background)
        moderation = kwargs.get("moderation", self.moderation)
        model_family = kwargs.get("model_family", self.model_family)
        if model_family not in ("gpt-image", "dall-e"):
            raise ValueError(
                "Azure image deployment '%s' has an invalid model_family (%r) — set "
                "image_generation.azure.model_family to exactly 'gpt-image' or "
                "'dall-e' in config/image.yaml (deployment names are user-defined "
                "and can't be inferred)." % (deployment, model_family)
            )
        is_gpt_image = model_family == "gpt-image"
        is_dalle = model_family == "dall-e"

        params: dict[str, Any] = {
            "model": deployment,
            "prompt": prompt,
            "n": 1,
            "size": size,
        }

        if is_gpt_image:
            params["quality"] = quality
            if output_format:
                params["output_format"] = output_format
            if output_compression is not None:
                params["output_compression"] = output_compression
            if background:
                params["background"] = background
            if moderation:
                params["moderation"] = moderation
        elif is_dalle:
            params["response_format"] = "b64_json"
            dalle_version = kwargs.get("dalle_version", self.dalle_version)
            if dalle_version not in ("dall-e-3", "dall-e-2"):
                raise ValueError(
                    "Azure image deployment '%s' has an invalid dalle_version (%r) — "
                    "set image_generation.azure.dalle_version to exactly 'dall-e-3' "
                    "or 'dall-e-2' in config/image.yaml." % (deployment, dalle_version)
                )
            # dall-e-2 rejects quality/style; only dall-e-3 accepts them.
            if dalle_version == "dall-e-3":
                params["quality"] = quality
                params["style"] = style

        try:
            response = await self.client.images.generate(**params)
            image_data = response.data[0]
            if not image_data.b64_json:
                raise ValueError("Azure OpenAI image generation did not return b64_json image data")

            image_bytes = base64.b64decode(image_data.b64_json)
            revised_prompt = getattr(image_data, "revised_prompt", None)

            # gpt-image deployments bill per token (response.usage); DALL-E
            # deployments bill per image instead (params["n"] above, always
            # 1) and report no usage.
            usage_dict = None
            media_usage = None
            usage = getattr(response, "usage", None)
            if is_gpt_image and usage is not None:
                prompt_tokens = getattr(usage, "input_tokens", None) or 0
                completion_tokens = getattr(usage, "output_tokens", None) or 0
                usage_dict = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "provider": self.provider_name,
                    "model": deployment,
                    "reported": True,
                }
            elif is_dalle:
                media_usage = {"unit": "images", "quantity": params["n"]}

            return {
                "image_bytes": image_bytes,
                "format": output_format if is_gpt_image and output_format else "png",
                "revised_prompt": revised_prompt,
                "usage": usage_dict,
                "media_usage": media_usage,
            }
        except Exception as e:
            self._handle_azure_error(e, "image generation")
            raise

    async def initialize(self) -> bool:
        """
        Initialize without AzureBaseService's inherited chat-completion probe
        (verify_connection() sends a chat.completions.create call against
        self.deployment) — an image-only Azure deployment rejects that
        request, which would make initialize() report failure and the
        image-service cache treat this provider as unavailable even though
        image generation itself works fine. Only client construction (done
        in AzureBaseService.__init__) is required to be "initialized".
        """
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        return self.initialized
