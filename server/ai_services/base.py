"""
Base classes for all AI services.

This module provides the foundational abstract classes that all AI services
inherit from, enabling a unified architecture across embeddings, inference,
moderation, reranking, vision, and audio services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TypeVar, Generic
import logging
from enum import Enum

T = TypeVar('T')


class ServiceType(Enum):
    """Enumeration of supported AI service types."""
    EMBEDDING = "embedding"
    INFERENCE = "inference"
    MODERATION = "moderation"
    RERANKING = "reranking"
    VISION = "vision"
    AUDIO = "audio"


class AIService(ABC, Generic[T]):
    """
    Base class for all AI services.

    This class provides the common interface and lifecycle management
    for all AI services in the Orbit system.

    Attributes:
        config: Configuration dictionary for the service
        service_type: Type of AI service (embedding, inference, etc.)
        logger: Logger instance for this service
        initialized: Whether the service has been initialized
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType):
        """
        Initialize the AI service.

        Args:
            config: Configuration dictionary for the service
            service_type: Type of AI service
        """
        self.config = config
        self.service_type = service_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.initialized = False

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the service and establish any necessary connections.

        Returns:
            True if initialization was successful, False otherwise
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close the service and release any resources.

        This should clean up connections, sessions, and any other
        resources held by the service.
        """
        pass

    @abstractmethod
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the service.

        Returns:
            True if the connection is working, False otherwise
        """
        pass


class ProviderAIService(AIService[T]):
    """
    Base class for provider-specific AI services.

    This class extends AIService with provider-specific functionality
    such as API key management, base URL configuration, and client initialization.

    Attributes:
        provider_name: Name of the provider (e.g., 'openai', 'anthropic')
        api_key: API key for the provider
        base_url: Base URL for API requests
        model: Model identifier
        endpoint: API endpoint path
        client: Client instance for API communication
    """

    def __init__(
        self,
        config: Dict[str, Any],
        service_type: ServiceType,
        provider_name: str
    ):
        """
        Initialize the provider-specific AI service.

        Args:
            config: Configuration dictionary for the service
            service_type: Type of AI service
            provider_name: Name of the provider
        """
        super().__init__(config, service_type)
        self.provider_name = provider_name
        self.api_key: Optional[str] = None
        self.base_url: Optional[str] = None
        self.model: Optional[str] = None
        self.endpoint: Optional[str] = None
        self.client: Optional[Any] = None

    def _extract_provider_config(self) -> Dict[str, Any]:
        """
        Extract provider-specific configuration from the config dictionary.

        This method looks for configuration in the following locations:
        1. config[service_type.value][provider_name] (preferred)
        2. config[provider_name] (fallback)

        Returns:
            Provider-specific configuration dictionary
        """
        # Try service-specific provider config first
        service_config = self.config.get(self.service_type.value, {})
        provider_config = service_config.get(self.provider_name, {})

        # Fallback to top-level provider config
        if not provider_config:
            provider_config = self.config.get(self.provider_name, {})

        return provider_config

    def _resolve_api_key(self, env_var_name: str, config_key: str = 'api_key') -> Optional[str]:
        """
        Resolve API key from environment variable or configuration.

        The resolution order is:
        1. Environment variable (if set)
        2. Config value (if present and not a template)
        3. Resolve template if config contains ${VAR_NAME}

        Args:
            env_var_name: Name of the environment variable to check
            config_key: Key in the config dictionary (default: 'api_key')

        Returns:
            Resolved API key or None if not found
        """
        import os

        # First try environment variable
        api_key = os.environ.get(env_var_name)
        if api_key:
            return api_key

        # Try to get from config
        provider_config = self._extract_provider_config()
        config_value = provider_config.get(config_key)

        if not config_value:
            return None

        # If it's a template like ${ENV_VAR}, resolve it
        if isinstance(config_value, str) and config_value.startswith('${') and config_value.endswith('}'):
            env_var = config_value[2:-1]  # Remove ${ and }
            return os.environ.get(env_var)

        return config_value

    def _get_base_url(self, default_url: str) -> str:
        """
        Get base URL from configuration or use default.

        Args:
            default_url: Default URL to use if not configured

        Returns:
            Base URL for API requests
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('base_url', default_url)

    def _get_model(self, default_model: Optional[str] = None) -> Optional[str]:
        """
        Get model identifier from configuration.

        Args:
            default_model: Default model to use if not configured

        Returns:
            Model identifier
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('model', default_model)

    def _get_endpoint(self, default_endpoint: str) -> str:
        """
        Get API endpoint from configuration or use default.

        This supports configurable endpoints for easy API version updates.

        Args:
            default_endpoint: Default endpoint to use if not configured

        Returns:
            API endpoint path
        """
        provider_config = self._extract_provider_config()

        # Check for endpoint in configuration
        endpoint = provider_config.get('endpoint')
        if endpoint:
            return endpoint

        # Check for endpoints dictionary (for multiple endpoints)
        endpoints = provider_config.get('endpoints', {})
        if endpoints and self.service_type:
            # Try to get service-specific endpoint
            service_endpoint = endpoints.get(self.service_type.value)
            if service_endpoint:
                return service_endpoint

        # Use default endpoint
        return default_endpoint

    def _get_timeout_config(self) -> Dict[str, int]:
        """
        Get timeout configuration from provider config.

        Returns:
            Dictionary with timeout settings (connect, total, warmup)
        """
        provider_config = self._extract_provider_config()
        timeout_config = provider_config.get('timeout', {})

        return {
            'connect': timeout_config.get('connect', 10000),  # 10s default
            'total': timeout_config.get('total', 60000),      # 60s default
            'warmup': timeout_config.get('warmup', 45000)     # 45s default
        }

    def _get_retry_config(self) -> Dict[str, Any]:
        """
        Get retry configuration from provider config.

        Returns:
            Dictionary with retry settings
        """
        provider_config = self._extract_provider_config()
        retry_config = provider_config.get('retry', {})

        return {
            'enabled': retry_config.get('enabled', False),
            'max_retries': retry_config.get('max_retries', 3),
            'initial_wait_ms': retry_config.get('initial_wait_ms', 1000),
            'max_wait_ms': retry_config.get('max_wait_ms', 30000),
            'exponential_base': retry_config.get('exponential_base', 2)
        }
