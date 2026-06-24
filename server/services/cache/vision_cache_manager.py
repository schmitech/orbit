"""
Vision Cache Manager for managing vision service instances.

Provides thread-safe caching and lifecycle management for vision services.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .service_cache_manager import ServiceCacheManager

logger = logging.getLogger(__name__)


class VisionCacheManager(ServiceCacheManager):
    """
    Manages vision service cache with thread-safe access.

    Responsibilities:
    - Cache vision service instances
    - Handle vision service creation
    - Provide thread-safe service access
    - Manage service lifecycle
    """

    service_label = "vision service"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the vision cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        super().__init__(config, thread_pool)

    def build_cache_key(self, provider_name: str) -> str:
        """
        Build cache key for a vision service.

        Args:
            provider_name: Name of the vision provider

        Returns:
            Cache key string
        """
        vision_config = self.config.get('vision', {}).get(provider_name, {})
        model = vision_config.get('model', '')
        return f"{provider_name}:{model}" if model else provider_name

    async def create_service(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None
    ) -> Any:
        """
        Create and cache a new vision service instance.

        Args:
            provider_name: Name of the vision provider
            adapter_name: Optional adapter name for context

        Returns:
            The created service instance
        """
        cache_key = self.build_cache_key(provider_name)
        return await self._create_cached_service(cache_key, provider_name, adapter_name)

    async def _create_instance(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        adapter_context = f" for adapter '{adapter_name}'" if adapter_name else ""
        vision_config = self.config.get('vision', {}).get(provider_name, {})
        model = vision_config.get('model', '')

        if model:
            logger.debug(f"Loading vision service '{provider_name}/{model}'{adapter_context}")
        else:
            logger.debug(f"Loading vision service '{provider_name}'{adapter_context}")

        try:
            from server.ai_services.services.vision_service import create_vision_service
        except ImportError:
            from ai_services.services.vision_service import create_vision_service

        return create_vision_service(provider_name, self.config)
