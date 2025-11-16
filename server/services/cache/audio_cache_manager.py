"""
Audio Cache Manager for managing audio service instances.

Provides thread-safe caching and lifecycle management for audio services (TTS/STT).
"""

import asyncio
import logging
import threading
from typing import Any, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class AudioCacheManager:
    """
    Manages audio service cache with thread-safe access.

    Responsibilities:
    - Cache audio service instances (TTS/STT)
    - Handle audio service creation
    - Provide thread-safe service access
    - Manage service lifecycle
    """

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the audio cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        self.config = config
        self._cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._initializing: Set[str] = set()
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=3)
        self.verbose = config.get('general', {}).get('verbose', False)

    def build_cache_key(self, provider_name: str) -> str:
        """
        Build cache key for an audio service.

        Args:
            provider_name: Name of the audio provider

        Returns:
            Cache key string
        """
        # Audio services can have separate TTS and STT models
        sound_config = self.config.get('sound', {}).get(provider_name, {})
        # Use TTS model as primary identifier, fall back to STT model
        model = sound_config.get('tts_model', sound_config.get('stt_model', ''))
        return f"{provider_name}:{model}" if model else provider_name

    def get(self, cache_key: str) -> Optional[Any]:
        """
        Get a cached audio service by key.

        Args:
            cache_key: Cache key for the service

        Returns:
            The cached service instance or None if not found
        """
        return self._cache.get(cache_key)

    def contains(self, cache_key: str) -> bool:
        """
        Check if an audio service is cached.

        Args:
            cache_key: Cache key for the service

        Returns:
            True if service is cached, False otherwise
        """
        return cache_key in self._cache

    def put(self, cache_key: str, service: Any) -> None:
        """
        Cache an audio service instance.

        Args:
            cache_key: Cache key for the service
            service: The service instance to cache
        """
        with self._cache_lock:
            self._cache[cache_key] = service

    async def remove(self, cache_key: str) -> Optional[Any]:
        """
        Remove an audio service from cache and clean up resources.

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
            if self.verbose:
                logger.debug(f"Audio service {cache_key} close method not available: {str(e)}")
        except Exception as e:
            logger.warning(f"Error closing audio service {cache_key}: {str(e)}")

        return service

    async def create_service(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None
    ) -> Any:
        """
        Create and cache a new audio service instance.

        Args:
            provider_name: Name of the audio provider
            adapter_name: Optional adapter name for context

        Returns:
            The created service instance
        """
        cache_key = self.build_cache_key(provider_name)

        # Check if already cached
        if cache_key in self._cache:
            if self.verbose:
                logger.debug(f"Using cached audio service: {cache_key}")
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
            sound_config = self.config.get('sound', {}).get(provider_name, {})
            tts_model = sound_config.get('tts_model', '')
            stt_model = sound_config.get('stt_model', '')

            model_info = []
            if tts_model:
                model_info.append(f"TTS:{tts_model}")
            if stt_model:
                model_info.append(f"STT:{stt_model}")

            if model_info:
                logger.info(f"Loading audio service '{provider_name}' ({', '.join(model_info)}){adapter_context}")
            else:
                logger.info(f"Loading audio service '{provider_name}'{adapter_context}")

            # Import the audio service factory
            try:
                from server.ai_services.services.audio_service import create_audio_service
            except ImportError:
                from ai_services.services.audio_service import create_audio_service

            # Create the audio service
            audio_service = create_audio_service(provider_name, self.config)

            # Initialize if needed
            if hasattr(audio_service, 'initialize'):
                if asyncio.iscoroutinefunction(audio_service.initialize):
                    await audio_service.initialize()
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._thread_pool, audio_service.initialize)

            # Cache the initialized service
            with self._cache_lock:
                self._cache[cache_key] = audio_service

            logger.info(f"Successfully cached audio service: {cache_key}{adapter_context}")
            return audio_service

        except Exception as e:
            logger.error(f"Failed to load audio service {provider_name}: {str(e)}")
            raise
        finally:
            with self._cache_lock:
                self._initializing.discard(cache_key)

    def get_cached_keys(self) -> list[str]:
        """
        Get list of cached audio service keys.

        Returns:
            List of cached service keys
        """
        return list(self._cache.keys())

    def get_cache_size(self) -> int:
        """
        Get the number of cached audio services.

        Returns:
            Number of cached services
        """
        return len(self._cache)

    async def clear(self) -> None:
        """Clear all cached audio services and clean up resources."""
        for cache_key in list(self._cache.keys()):
            await self.remove(cache_key)

        logger.info("Cleared all audio services from cache")

    async def close(self) -> None:
        """Clean up all resources."""
        await self.clear()
