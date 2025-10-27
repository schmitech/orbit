"""
Reranker Service Manager - Singleton factory for reranking services.

This module manages reranker service instances using the unified AI services architecture,
implementing singleton pattern for efficient service reuse across adapters.
"""

import logging
import threading
from typing import Dict, Any, Optional

try:
    from server.ai_services.factory import AIServiceFactory
    from server.ai_services.base import ServiceType
except ImportError:
    from ai_services.factory import AIServiceFactory
    from ai_services.base import ServiceType

logger = logging.getLogger(__name__)


class RerankingServiceManager:
    """
    Manager for reranking service instances.

    This class:
    - Creates reranking services using the unified AI services architecture
    - Implements singleton pattern to share services across adapters
    - Caches instances by provider + base_url + model combination
    - Supports adapter-level provider overrides
    - Thread-safe with locks
    """

    _instances: Dict[str, Any] = {}
    _lock = None

    @classmethod
    def _get_lock(cls):
        """Get or create the lock for thread safety."""
        if cls._lock is None:
            cls._lock = threading.Lock()
        return cls._lock

    @classmethod
    def create_reranker_service(cls, config: Dict[str, Any], provider_name: Optional[str] = None) -> Any:
        """
        Create or return a cached reranker service instance.

        Args:
            config: The full application configuration
            provider_name: Optional specific provider name to override the one in config

        Returns:
            An initialized reranker service instance (shared singleton)

        Raises:
            ValueError: If the specified provider is not supported or disabled
        """
        # Get the reranker provider - either specified or from config
        if not provider_name:
            provider_name = config.get('reranker', {}).get('provider', 'ollama')

        # Check if the provider is enabled
        provider_config = config.get('rerankers', {}).get(provider_name, {})
        if provider_config.get('enabled', True) is False:
            available = [p for p, cfg in config.get('rerankers', {}).items() 
                        if cfg.get('enabled', True) is not False]
            raise ValueError(
                f"Reranker provider '{provider_name}' is disabled in config. "
                f"Available enabled providers: {available}. "
                f"Please enable the provider in config/rerankers.yaml or use a different provider."
            )

        # Create a cache key that includes provider name and relevant config
        cache_key = cls._create_cache_key(provider_name, config)

        # Check if we already have this instance
        with cls._get_lock():
            if cache_key in cls._instances:
                logger.debug(f"Reusing cached reranker service: {provider_name}")
                return cls._instances[cache_key]

            # Create new instance
            logger.debug(f"Creating new reranker service instance: {provider_name}")
            instance = cls._create_new_instance(provider_name, config)
            cls._instances[cache_key] = instance
            return instance

    @staticmethod
    def _create_cache_key(provider_name: str, config: Dict[str, Any]) -> str:
        """
        Create a cache key for the reranker service based on provider and config.

        Args:
            provider_name: Name of the reranker provider
            config: Full application configuration

        Returns:
            Cache key string
        """
        # Include relevant config parameters that would affect the service instance
        provider_config = config.get('rerankers', {}).get(provider_name, {})

        # Create a key based on provider and key config parameters
        # For most providers, the base_url and model are the distinguishing factors
        base_url = provider_config.get('base_url', '')
        model = provider_config.get('model', '')

        return f"{provider_name}:{base_url}:{model}"

    @staticmethod
    def _create_new_instance(provider_name: str, config: Dict[str, Any]) -> Any:
        """
        Create a new reranker service instance using the unified AI services architecture.

        Args:
            provider_name: Name of the reranker provider
            config: Full application configuration

        Returns:
            Reranker service instance

        Raises:
            ValueError: If provider is not supported or service creation fails
        """
        # Use the unified AI services factory
        try:
            service = AIServiceFactory.create_service(
                ServiceType.RERANKING,
                provider_name,
                config,
                use_cache=False  # We handle caching ourselves
            )
            logger.info(f"Created reranker service: {provider_name}")
            return service

        except ValueError as e:
            # Check if service is registered
            if AIServiceFactory.is_service_registered(ServiceType.RERANKING, provider_name):
                logger.error(f"Failed to create reranker service '{provider_name}': {e}")
                raise
            else:
                available = AIServiceFactory.list_available_services().get('reranking', [])
                raise ValueError(
                    f"Reranker provider '{provider_name}' is not available. "
                    f"Available providers: {available}. "
                    f"Please check that the provider is enabled in config/rerankers.yaml"
                ) from e
        except Exception as e:
            logger.error(f"Unexpected error creating reranker service '{provider_name}': {e}")
            raise

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached reranker service instances. Useful for testing or reloading."""
        with cls._get_lock():
            cls._instances.clear()
            logger.info("Cleared all cached reranker service instances")

    @classmethod
    def get_cached_instance(cls, provider_name: str, config: Dict[str, Any]) -> Optional[Any]:
        """
        Get a cached reranker service instance if it exists.

        Args:
            provider_name: Name of the reranker provider
            config: Full application configuration

        Returns:
            Cached instance or None
        """
        cache_key = cls._create_cache_key(provider_name, config)
        with cls._get_lock():
            return cls._instances.get(cache_key)
