"""
Image Generation Cache Manager for managing image generation service instances.

Provides thread-safe caching and lifecycle management for image generation services.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .service_cache_manager import ServiceCacheManager

logger = logging.getLogger(__name__)


class ImageGenerationCacheManager(ServiceCacheManager):
    """Manages image generation service cache with thread-safe access."""

    service_label = "image generation service"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        super().__init__(config, thread_pool)

    def build_cache_key(self, provider_name: str) -> str:
        image_config = self.config.get('image_generation', {}).get(provider_name, {})
        model = image_config.get('model', '')
        return f"{provider_name}:{model}" if model else provider_name

    async def create_service(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
    ) -> Any:
        cache_key = self.build_cache_key(provider_name)
        return await self._create_cached_service(cache_key, provider_name, adapter_name)

    async def _create_instance(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        adapter_context = f" for adapter '{adapter_name}'" if adapter_name else ""
        image_config = self.config.get('image_generation', {}).get(provider_name, {})
        model = image_config.get('model', '')

        if model:
            logger.debug(f"Loading image generation service '{provider_name}/{model}'{adapter_context}")
        else:
            logger.debug(f"Loading image generation service '{provider_name}'{adapter_context}")

        try:
            from server.ai_services.factory import AIServiceFactory
            from server.ai_services.base import ServiceType
        except ImportError:
            from ai_services.factory import AIServiceFactory
            from ai_services.base import ServiceType

        return AIServiceFactory.create_service(
            ServiceType.IMAGE_GENERATION,
            provider_name,
            self.config,
            use_cache=False,
        )
