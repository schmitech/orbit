"""
Reranker Cache Manager for managing reranker service instances.

Provides thread-safe caching and lifecycle management for reranker services.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class RerankerCacheManager:
    """
    Manages reranker service cache with thread-safe access.

    Responsibilities:
    - Cache reranker service instances
    - Handle reranker service creation
    - Provide thread-safe service access
    - Manage service lifecycle
    """

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the reranker cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        self.config = config
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._initializing: Set[str] = set()
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=3)

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

    def get(self, cache_key: str) -> Optional[Any]:
        """
        Get a cached reranker service by key.

        Args:
            cache_key: Cache key for the service

        Returns:
            The cached service instance or None if not found
        """
        return self._cache.get(cache_key)

    def contains(self, cache_key: str) -> bool:
        """
        Check if a reranker service is cached.

        Args:
            cache_key: Cache key for the service

        Returns:
            True if service is cached, False otherwise
        """
        return cache_key in self._cache

    def put(self, cache_key: str, service: Any) -> None:
        """
        Cache a reranker service instance.

        Args:
            cache_key: Cache key for the service
            service: The service instance to cache
        """
        with self._cache_lock:
            self._cache[cache_key] = service

    async def remove(self, cache_key: str) -> Optional[Any]:
        """
        Remove a reranker service from cache and clean up resources.

        Args:
            cache_key: Cache key for the service

        Returns:
            The removed service instance or None if not found
        """
        with self._cache_lock:
            if cache_key not in self._cache:
                return None

            service = self._cache.pop(cache_key)
            self._initializing.discard(cache_key)

        # Try to close the service if it has a close method
        try:
            if hasattr(service, 'close') and callable(getattr(service, 'close', None)):
                if asyncio.iscoroutinefunction(service.close):
                    await service.close()
                else:
                    service.close()
        except (AttributeError, TypeError) as e:
            logger.debug(f"Reranker service {cache_key} close method not available: {str(e)}")
        except Exception as e:
            logger.warning(f"Error closing reranker service {cache_key}: {str(e)}")

        return service

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

        # Check if already cached
        if cache_key in self._cache:
            logger.debug(f"Using cached reranker service: {cache_key}")
            return self._cache[cache_key]

        # Try to claim initialization ownership
        should_initialize = False
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
            if cache_key not in self._initializing:
                self._initializing.add(cache_key)
                should_initialize = True

        # If someone else is initializing, wait for them
        if not should_initialize:
            while True:
                await asyncio.sleep(0.1)
                with self._cache_lock:
                    if cache_key in self._cache:
                        return self._cache[cache_key]
                    if cache_key not in self._initializing:
                        self._initializing.add(cache_key)
                        should_initialize = True
                        break

        try:
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

            # Create the reranker service
            reranker_service = RerankingServiceManager.create_reranker_service(
                self.config,
                provider_name
            )

            # Initialize if needed
            if hasattr(reranker_service, 'initialize'):
                if asyncio.iscoroutinefunction(reranker_service.initialize):
                    await reranker_service.initialize()
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._thread_pool, reranker_service.initialize)

            # Cache the initialized service
            with self._cache_lock:
                self._cache[cache_key] = reranker_service

            logger.info(f"Successfully cached reranker service: {cache_key}{adapter_context}")
            return reranker_service

        except Exception as e:
            logger.error(f"Failed to load reranker service {provider_name}: {str(e)}")
            raise
        finally:
            with self._cache_lock:
                self._initializing.discard(cache_key)

    def get_cached_keys(self) -> list[str]:
        """
        Get list of cached reranker service keys.

        Returns:
            List of cached service keys
        """
        return list(self._cache.keys())

    def get_cache_size(self) -> int:
        """
        Get the number of cached reranker services.

        Returns:
            Number of cached services
        """
        return len(self._cache)

    async def clear(self) -> None:
        """Clear all cached reranker services and clean up resources."""
        for cache_key in list(self._cache.keys()):
            await self.remove(cache_key)

        logger.info("Cleared all reranker services from cache")

    async def close(self) -> None:
        """Clean up all resources."""
        await self.clear()
