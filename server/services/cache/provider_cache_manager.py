"""
Provider Cache Manager for managing inference provider instances.

Provides thread-safe caching and lifecycle management for inference providers.
"""

import asyncio
import copy
import logging
import threading
from typing import Any, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class ProviderCacheManager:
    """
    Manages inference provider cache with thread-safe access.

    Responsibilities:
    - Cache provider instances with model-specific keys
    - Handle provider creation with model overrides
    - Provide thread-safe provider access
    - Manage provider lifecycle
    """

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the provider cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        self.config = config
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._initializing: Set[str] = set()
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=3)

    def build_cache_key(self, provider_name: str, model_override: Optional[str] = None) -> str:
        """
        Build cache key for a provider with optional model override.

        Args:
            provider_name: Name of the provider
            model_override: Optional model name override

        Returns:
            Cache key string
        """
        if model_override:
            return f"{provider_name}:{model_override}"
        return provider_name

    def get(self, cache_key: str) -> Optional[Any]:
        """
        Get a cached provider by key.

        Args:
            cache_key: Cache key for the provider

        Returns:
            The cached provider instance or None if not found
        """
        return self._cache.get(cache_key)

    def contains(self, cache_key: str) -> bool:
        """
        Check if a provider is cached.

        Args:
            cache_key: Cache key for the provider

        Returns:
            True if provider is cached, False otherwise
        """
        return cache_key in self._cache

    def put(self, cache_key: str, provider: Any) -> None:
        """
        Cache a provider instance.

        Args:
            cache_key: Cache key for the provider
            provider: The provider instance to cache
        """
        with self._cache_lock:
            self._cache[cache_key] = provider

    async def remove(self, cache_key: str) -> Optional[Any]:
        """
        Remove a provider from cache and clean up resources.

        Args:
            cache_key: Cache key for the provider

        Returns:
            The removed provider instance or None if not found
        """
        with self._cache_lock:
            if cache_key not in self._cache:
                return None

            provider = self._cache.pop(cache_key)
            self._initializing.discard(cache_key)

        # Try to close the provider if it has a close method
        try:
            if hasattr(provider, 'close') and callable(getattr(provider, 'close', None)):
                if asyncio.iscoroutinefunction(provider.close):
                    await provider.close()
                else:
                    provider.close()
        except (AttributeError, TypeError) as e:
            logger.debug(f"Provider {cache_key} close method not available: {str(e)}")
        except Exception as e:
            logger.warning(f"Error closing provider {cache_key}: {str(e)}")

        return provider

    async def remove_by_prefix(self, prefix: str) -> list[str]:
        """
        Remove all providers with keys matching the given prefix.

        Args:
            prefix: Prefix to match (e.g., provider name)

        Returns:
            List of removed cache keys
        """
        removed_keys = []
        with self._cache_lock:
            keys_to_remove = [
                key for key in list(self._cache.keys())
                if key == prefix or key.startswith(f"{prefix}:")
            ]

        for key in keys_to_remove:
            await self.remove(key)
            removed_keys.append(key)

        return removed_keys

    async def create_provider(
        self,
        provider_name: str,
        model_override: Optional[str] = None,
        adapter_name: Optional[str] = None
    ) -> Any:
        """
        Create and cache a new provider instance.

        Args:
            provider_name: Name of the provider to create
            model_override: Optional model name override
            adapter_name: Optional adapter name for context

        Returns:
            The created provider instance
        """
        cache_key = self.build_cache_key(provider_name, model_override)

        # Check if already cached
        if cache_key in self._cache:
            logger.debug(f"Using cached provider: {cache_key}")
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
            # Prepare config with model override if specified
            config_for_provider = copy.deepcopy(self.config)

            if model_override:
                if 'inference' not in config_for_provider:
                    config_for_provider['inference'] = {}
                if provider_name not in config_for_provider['inference']:
                    config_for_provider['inference'][provider_name] = {}

                config_for_provider['inference'][provider_name]['model'] = model_override
                logger.info(f"Loading inference provider '{provider_name}' with model override: {model_override}")
            else:
                logger.info(f"Loading inference provider '{provider_name}' with default model")

            try:
                from server.inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory
            except ImportError:
                from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory

            # Create and initialize the provider
            provider = ProviderFactory.create_provider_by_name(provider_name, config_for_provider)
            if hasattr(provider, 'initialize'):
                if asyncio.iscoroutinefunction(provider.initialize):
                    await provider.initialize()
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._thread_pool, provider.initialize)

            # Cache the initialized provider
            with self._cache_lock:
                self._cache[cache_key] = provider

            logger.info(f"Successfully cached inference provider: {cache_key}")
            return provider

        except Exception as e:
            logger.error(f"Failed to load provider {provider_name}: {str(e)}")
            raise
        finally:
            with self._cache_lock:
                self._initializing.discard(cache_key)

    def get_cached_keys(self) -> list[str]:
        """
        Get list of cached provider keys.

        Returns:
            List of cached provider keys
        """
        return list(self._cache.keys())

    def get_cache_size(self) -> int:
        """
        Get the number of cached providers.

        Returns:
            Number of cached providers
        """
        return len(self._cache)

    async def clear(self) -> None:
        """Clear all cached providers and clean up resources."""
        for cache_key in list(self._cache.keys()):
            await self.remove(cache_key)

        logger.info("Cleared all providers from cache")

    async def close(self) -> None:
        """Clean up all resources."""
        await self.clear()
