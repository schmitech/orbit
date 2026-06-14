"""
Reranker Cache Manager for managing reranker service instances.

Provides thread-safe caching and lifecycle management for reranker services.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .service_cache_manager import ServiceCacheManager

logger = logging.getLogger(__name__)


class RerankerCacheManager(ServiceCacheManager):
    """
    Manages reranker service cache with thread-safe access.

    Responsibilities:
    - Cache reranker service instances
    - Handle reranker service creation
    - Provide thread-safe service access
    - Manage service lifecycle
    """

    service_label = "reranker service"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the reranker cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        super().__init__(config, thread_pool)

    def build_cache_key(self, provider_name: str) -> str:
        """
        Build cache key for a reranker service.

        Args:
            provider_name: Name of the reranker provider

        Returns:
            Cache key string
        """
        reranker_config = self.config.get('rerankers', {}).get(provider_name, {})
        model = reranker_config.get('model', '')
        return f"{provider_name}:{model}" if model else provider_name

    async def create_service(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None
    ) -> Any:
        """
        Create and cache a new reranker service instance.

        Args:
            provider_name: Name of the reranker provider
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
        reranker_config = self.config.get('rerankers', {}).get(provider_name, {})
        model = reranker_config.get('model', '')

        if model:
            logger.info(f"Loading reranker service '{provider_name}/{model}'{adapter_context}")
        else:
            logger.info(f"Loading reranker service '{provider_name}'{adapter_context}")

        try:
            from server.services.reranker_service_manager import RerankingServiceManager
        except ImportError:
            from services.reranker_service_manager import RerankingServiceManager

        return RerankingServiceManager.create_reranker_service(
            self.config,
            provider_name
        )
