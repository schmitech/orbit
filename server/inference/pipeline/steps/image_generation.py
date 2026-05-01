"""
Image Generation Step

Generates an image from the user's prompt when the adapter is of type
'image_generation'. Replaces LLMInferenceStep for such adapters.
"""

import base64
import logging
from typing import Optional, Dict, Any

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


class ImageGenerationStep(PipelineStep):
    """
    Generate an image from the user's text prompt.

    Executes only for adapters whose 'type' is 'image_generation'.
    Stores the result in context.image (base64), context.image_format,
    and context.image_revised_prompt.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'image_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        image_service = await self._get_image_service(context)
        if image_service is None:
            context.set_error("No image generation service is available for this adapter.")
            return context

        try:
            result = await image_service.generate_image(context.message)
            context.image = base64.b64encode(result["image_bytes"]).decode("utf-8")
            context.image_format = result.get("format", "png")
            context.image_revised_prompt = result.get("revised_prompt")
            # Set response to the revised prompt (if any) so conversation history
            # stores something meaningful; falls back to the original prompt.
            context.response = context.image_revised_prompt or context.message
        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            context.set_error(f"Image generation failed: {e}")

        return context

    async def _get_image_service(self, context: ProcessingContext):
        """Resolve the image generation service from config and adapter settings."""
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType

        config = self.container.get_or_none('config') or {}

        # Determine provider: adapter override > global default
        provider = self._resolve_provider(context, config)
        if not provider:
            logger.warning("No image generation provider configured.")
            return None

        service = await AIServiceFactory.create_and_initialize_service(
            ServiceType.IMAGE_GENERATION,
            provider,
            config,
            use_cache=True,
        )
        return service

    def _resolve_provider(self, context: ProcessingContext, config: Dict[str, Any]) -> Optional[str]:
        """Return the provider name for this request."""
        # Allow adapter config to override the global default
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config:
                    provider = adapter_config.get('image_provider')
                    if provider:
                        return provider
            except Exception:
                pass

        return config.get('image', {}).get('provider')
