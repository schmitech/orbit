"""
Audio Cache Manager for managing audio service instances.

Provides thread-safe caching and lifecycle management for audio services (TTS/STT).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .service_cache_manager import ServiceCacheManager

logger = logging.getLogger(__name__)


class AudioCacheManager(ServiceCacheManager):
    """
    Manages audio service cache with thread-safe access.

    Responsibilities:
    - Cache audio service instances (TTS/STT)
    - Handle audio service creation
    - Provide thread-safe service access
    - Manage service lifecycle
    """

    service_label = "audio service"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the audio cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        super().__init__(config, thread_pool)

    def build_cache_key(self, provider_name: str) -> str:
        """
        Build cache key for an audio service.

        Uses config from tts.yaml and stt.yaml.

        Args:
            provider_name: Name of the audio provider

        Returns:
            Cache key string
        """
        tts_model, stt_model = self._get_models(provider_name)
        model = tts_model or stt_model
        return f"{provider_name}:{model}" if model else provider_name

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
        return await self._create_cached_service(cache_key, provider_name, adapter_name)

    async def _create_instance(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        adapter_context = f" for adapter '{adapter_name}'" if adapter_name else ""
        model_info = self._get_model_info(provider_name)

        if model_info:
            logger.debug(f"Loading audio service '{provider_name}' ({', '.join(model_info)}){adapter_context}")
        else:
            logger.debug(f"Loading audio service '{provider_name}'{adapter_context}")

        try:
            from server.ai_services.services.audio_service import create_audio_service
        except ImportError:
            from ai_services.services.audio_service import create_audio_service

        try:
            return create_audio_service(provider_name, self.config)
        except ValueError as e:
            if self._is_audio_disabled():
                logger.info(
                    f"Audio service '{provider_name}' not available{adapter_context} - "
                    f"audio is globally disabled"
                )
            else:
                logger.warning(
                    f"Audio service '{provider_name}' not available{adapter_context}: {str(e)}"
                )
            raise

    def _get_models(self, provider_name: str) -> tuple[str, str]:
        tts_providers_config = self.config.get('tts_providers', {})
        stt_providers_config = self.config.get('stt_providers', {})
        tts_model = tts_providers_config.get(provider_name, {}).get('tts_model', '')
        stt_model = stt_providers_config.get(provider_name, {}).get('stt_model', '')
        return tts_model, stt_model

    def _get_model_info(self, provider_name: str) -> list[str]:
        tts_model, stt_model = self._get_models(provider_name)
        model_info = []
        if tts_model:
            model_info.append(f"TTS:{tts_model}")
        if stt_model:
            model_info.append(f"STT:{stt_model}")
        return model_info

    def _is_audio_disabled(self) -> bool:
        return self._is_disabled(self.config.get('tts', {})) and self._is_disabled(self.config.get('stt', {}))

    def _log_create_error(self, provider_name: str, error: Exception) -> None:
        if isinstance(error, ValueError):
            return

        super()._log_create_error(provider_name, error)

    @staticmethod
    def _is_disabled(section: Dict[str, Any]) -> bool:
        enabled = section.get('enabled', True)
        return enabled is False or (isinstance(enabled, str) and enabled.lower() == 'false')
