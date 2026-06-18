"""
Base cache manager for service instances.

Provides shared thread-safe caching, initialization coordination, and lifecycle
management for provider-like service caches.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class _InitializationState:
    event: asyncio.Event
    cancelled: bool = False


class _InitializationCancelled(RuntimeError):
    """Raised when an in-flight initialization is invalidated by removal."""


class ServiceCacheManager:
    """Shared implementation for service cache managers."""

    service_label = "service"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        self.config = config
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._initializing: Dict[str, _InitializationState] = {}
        self._owns_pool = thread_pool is None
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=3)

    def get(self, cache_key: str) -> Optional[Any]:
        """Get a cached service by key."""
        with self._cache_lock:
            return self._cache.get(cache_key)

    def contains(self, cache_key: str) -> bool:
        """Check if a service is cached."""
        with self._cache_lock:
            return cache_key in self._cache

    def put(self, cache_key: str, service: Any) -> None:
        """Cache a service instance."""
        with self._cache_lock:
            self._cache[cache_key] = service

    async def remove(self, cache_key: str, close_service: bool = True) -> Optional[Any]:
        """Remove a service from cache and optionally close it."""
        with self._cache_lock:
            service = self._cache.pop(cache_key, None)
            state = self._initializing.pop(cache_key, None)

        if state is not None:
            state.cancelled = True
            state.event.set()

        if service is None:
            return None

        if close_service:
            await self._close_service(cache_key, service)

        return service

    async def _remove_matching(self, predicate: Callable[[str], bool]) -> list[str]:
        """Atomically remove cached services whose keys match a predicate."""
        with self._cache_lock:
            entries = [
                (key, self._cache.pop(key))
                for key in list(self._cache.keys())
                if predicate(key)
            ]
            initializing_states = [
                self._initializing.pop(key)
                for key in list(self._initializing.keys())
                if predicate(key)
            ]

        for state in initializing_states:
            state.cancelled = True
            state.event.set()

        for key, service in entries:
            await self._close_service(key, service)

        return [key for key, _service in entries]

    async def _create_cached_service(
        self,
        cache_key: str,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Create and cache a service, sharing in-flight initialization by key."""
        while True:
            with self._cache_lock:
                if cache_key in self._cache:
                    logger.debug(f"Using cached {self.service_label}: {cache_key}")
                    return self._cache[cache_key]

                state = self._initializing.get(cache_key)
                if state is None:
                    state = _InitializationState(event=asyncio.Event())
                    self._initializing[cache_key] = state
                    break

            await state.event.wait()

        try:
            service = await self._create_instance(
                provider_name,
                adapter_name=adapter_name,
                **kwargs,
            )
            await self._initialize_service(service)

            with self._cache_lock:
                if self._initializing.get(cache_key) is not state or state.cancelled:
                    should_cache = False
                else:
                    self._cache[cache_key] = service
                    should_cache = True

            if not should_cache:
                await self._close_service(cache_key, service)
                raise _InitializationCancelled(
                    f"{self.service_label.capitalize()} initialization for {cache_key} was cancelled"
                )

            logger.info(f"Successfully cached {self.service_label}: {cache_key}")
            return service
        except _InitializationCancelled:
            raise
        except Exception as e:
            self._log_create_error(provider_name, e)
            raise
        finally:
            with self._cache_lock:
                current_state = self._initializing.get(cache_key)
                if current_state is state:
                    self._initializing.pop(cache_key, None)
                else:
                    current_state = None
            if current_state is not None:
                current_state.event.set()

    async def _initialize_service(self, service: Any) -> None:
        if not hasattr(service, 'initialize'):
            return

        if asyncio.iscoroutinefunction(service.initialize):
            result = await service.initialize()
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(self._thread_pool, service.initialize)

        if result is False:
            raise RuntimeError(f"{self.service_label.capitalize()} initialization returned False")

    async def _close_service(self, cache_key: str, service: Any) -> None:
        try:
            if hasattr(service, 'close') and callable(getattr(service, 'close', None)):
                if asyncio.iscoroutinefunction(service.close):
                    await service.close()
                else:
                    service.close()
        except (AttributeError, TypeError) as e:
            logger.debug(f"{self.service_label.capitalize()} {cache_key} close method not available: {str(e)}")
        except Exception as e:
            logger.warning(f"Error closing {self.service_label} {cache_key}: {str(e)}")

    def _log_create_error(self, provider_name: str, error: Exception) -> None:
        logger.error(f"Failed to load {self.service_label} {provider_name}: {str(error)}")

    def get_cached_keys(self) -> list[str]:
        """Get list of cached service keys."""
        with self._cache_lock:
            return list(self._cache.keys())

    def get_cache_size(self) -> int:
        """Get the number of cached services."""
        with self._cache_lock:
            return len(self._cache)

    async def clear(self) -> None:
        """Clear all cached services and clean up resources."""
        for cache_key in self.get_cached_keys():
            await self.remove(cache_key)

        logger.info(f"Cleared all {self.service_label}s from cache")

    async def close(self) -> None:
        """Clean up all resources."""
        await self.clear()
        if self._owns_pool:
            self._thread_pool.shutdown(wait=False)

    async def _create_instance(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError
