"""
Adapter Cache Manager for managing adapter instances.

Provides thread-safe caching and lifecycle management for adapter instances.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


class AdapterCacheManager:
    """
    Manages adapter instances cache with thread-safe access.

    Responsibilities:
    - Cache adapter instances
    - Track adapter initialization state
    - Provide thread-safe adapter access
    - Handle adapter lifecycle (load, unload, close)
    """

    def __init__(self):
        """Initialize the adapter cache manager."""
        self._cache: Dict[str, Any] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._cache_lock = threading.Lock()
        self._initializing: Set[str] = set()

    def get(self, adapter_name: str) -> Optional[Any]:
        """
        Get a cached adapter by name.

        Args:
            adapter_name: Name of the adapter

        Returns:
            The cached adapter instance or None if not found
        """
        return self._cache.get(adapter_name)

    def contains(self, adapter_name: str) -> bool:
        """
        Check if an adapter is cached.

        Args:
            adapter_name: Name of the adapter

        Returns:
            True if adapter is cached, False otherwise
        """
        return adapter_name in self._cache

    def put(self, adapter_name: str, adapter: Any) -> None:
        """
        Cache an adapter instance.

        Args:
            adapter_name: Name of the adapter
            adapter: The adapter instance to cache
        """
        with self._cache_lock:
            self._cache[adapter_name] = adapter
            self._locks[adapter_name] = threading.Lock()

    async def remove(self, adapter_name: str) -> Optional[Any]:
        """
        Remove an adapter from cache and clean up resources.

        Args:
            adapter_name: Name of the adapter to remove

        Returns:
            The removed adapter instance or None if not found
        """
        with self._cache_lock:
            if adapter_name not in self._cache:
                return None

            adapter = self._cache.pop(adapter_name)
            self._locks.pop(adapter_name, None)

        # Try to close the adapter if it has a close method
        try:
            if hasattr(adapter, 'close'):
                if asyncio.iscoroutinefunction(adapter.close):
                    await adapter.close()
                else:
                    adapter.close()
        except Exception as e:
            logger.warning(f"Error closing adapter {adapter_name}: {str(e)}")

        # Release datasource reference if applicable
        try:
            if (hasattr(adapter, '_datasource') and adapter._datasource is not None and
                hasattr(adapter, '_datasource_name') and hasattr(adapter, '_datasource_config_for_release')):
                from datasources.registry import get_registry as get_datasource_registry
                datasource_registry = get_datasource_registry()
                datasource_registry.release_datasource(
                    datasource_name=adapter._datasource_name,
                    config=adapter._datasource_config_for_release,
                    logger_instance=logger
                )
        except Exception as e:
            logger.warning(f"Error releasing datasource for adapter {adapter_name}: {str(e)}")

        # Unregister capabilities
        try:
            from adapters.capabilities import get_capability_registry
            capability_registry = get_capability_registry()
            capability_registry.unregister(adapter_name)
        except Exception as e:
            logger.warning(f"Error unregistering capabilities for adapter {adapter_name}: {str(e)}")

        logger.info(f"Removed adapter from cache: {adapter_name}")
        return adapter

    def get_cached_names(self) -> list[str]:
        """
        Get list of cached adapter names.

        Returns:
            List of cached adapter names
        """
        return list(self._cache.keys())

    def get_cache_size(self) -> int:
        """
        Get the number of cached adapters.

        Returns:
            Number of cached adapters
        """
        return len(self._cache)

    async def clear(self) -> None:
        """Clear all cached adapters and clean up resources."""
        adapter_names = list(self._cache.keys())

        for adapter_name in adapter_names:
            await self.remove(adapter_name)

        # Clear all capabilities from registry
        try:
            from adapters.capabilities import get_capability_registry
            capability_registry = get_capability_registry()
            capability_registry.clear()
        except Exception as e:
            logger.warning(f"Error clearing capability registry: {str(e)}")

        logger.info("Cleared all adapters from cache")

    def claim_initialization(self, adapter_name: str) -> bool:
        """
        Attempt to claim ownership of adapter initialization.

        Args:
            adapter_name: Name of the adapter to initialize

        Returns:
            True if initialization ownership was claimed, False if already being initialized
        """
        with self._cache_lock:
            if adapter_name in self._cache:
                return False
            if adapter_name not in self._initializing:
                self._initializing.add(adapter_name)
                return True
            return False

    def release_initialization(self, adapter_name: str) -> None:
        """
        Release initialization ownership.

        Args:
            adapter_name: Name of the adapter
        """
        with self._cache_lock:
            self._initializing.discard(adapter_name)

    def is_initializing(self, adapter_name: str) -> bool:
        """
        Check if an adapter is currently being initialized.

        Args:
            adapter_name: Name of the adapter

        Returns:
            True if adapter is being initialized, False otherwise
        """
        return adapter_name in self._initializing

    def get_initializing_count(self) -> int:
        """
        Get the number of adapters currently being initialized.

        Returns:
            Number of adapters being initialized
        """
        return len(self._initializing)
