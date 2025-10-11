"""
Unified factory for all AI services.

This module provides a centralized factory for creating and managing
AI service instances across all service types (embeddings, inference,
moderation, reranking, vision, audio) and providers (OpenAI, Anthropic,
Ollama, Cohere, Mistral, etc.).
"""

from typing import Dict, Any, Type, Optional, Tuple
import logging

from .base import AIService, ServiceType

logger = logging.getLogger(__name__)


class AIServiceFactory:
    """
    Unified factory for creating AI service instances.

    This factory implements a registry pattern where service implementations
    can be registered and then instantiated on demand. It supports:
    - Service registration by (service_type, provider) pair
    - Service instantiation with configuration
    - Singleton pattern for service instances
    - Service lifecycle management
    """

    # Registry mapping (service_type, provider) -> service_class
    _service_registry: Dict[Tuple[ServiceType, str], Type[AIService]] = {}

    # Cache for singleton instances
    _service_cache: Dict[Tuple[ServiceType, str], AIService] = {}

    @classmethod
    def register_service(
        cls,
        service_type: ServiceType,
        provider: str,
        service_class: Type[AIService]
    ) -> None:
        """
        Register a service implementation.

        Args:
            service_type: Type of AI service (embedding, inference, etc.)
            provider: Provider name (openai, anthropic, etc.)
            service_class: Class to instantiate for this service/provider pair

        Example:
            >>> AIServiceFactory.register_service(
            ...     ServiceType.EMBEDDING,
            ...     "openai",
            ...     OpenAIEmbeddingService
            ... )
        """
        key = (service_type, provider)

        if key in cls._service_registry:
            logger.warning(
                f"Overwriting existing registration for {service_type.value} "
                f"service with provider {provider}"
            )

        cls._service_registry[key] = service_class
        logger.debug(
            f"Registered {service_class.__name__} for {service_type.value} "
            f"service with provider {provider}"
        )

    @classmethod
    def create_service(
        cls,
        service_type: ServiceType,
        provider: str,
        config: Dict[str, Any],
        use_cache: bool = True
    ) -> AIService:
        """
        Create a service instance.

        Args:
            service_type: Type of AI service
            provider: Provider name
            config: Configuration dictionary
            use_cache: If True, return cached instance if available

        Returns:
            Service instance

        Raises:
            ValueError: If no service is registered for the given type/provider

        Example:
            >>> factory = AIServiceFactory()
            >>> embedding_service = factory.create_service(
            ...     ServiceType.EMBEDDING,
            ...     "openai",
            ...     config
            ... )
        """
        key = (service_type, provider)

        # Check cache first if requested
        if use_cache and key in cls._service_cache:
            logger.debug(
                f"Returning cached instance for {service_type.value} "
                f"service with provider {provider}"
            )
            return cls._service_cache[key]

        # Check if service is registered
        if key not in cls._service_registry:
            available = cls.list_available_services()
            raise ValueError(
                f"No service registered for {service_type.value} with provider {provider}. "
                f"Available services: {available}"
            )

        # Instantiate the service
        service_class = cls._service_registry[key]

        try:
            service_instance = service_class(config)

            # Cache if requested
            if use_cache:
                cls._service_cache[key] = service_instance

            logger.info(
                f"Created {service_class.__name__} for {service_type.value} "
                f"service with provider {provider}"
            )

            return service_instance

        except Exception as e:
            logger.error(
                f"Failed to create {service_type.value} service with provider "
                f"{provider}: {str(e)}"
            )
            raise

    @classmethod
    async def create_and_initialize_service(
        cls,
        service_type: ServiceType,
        provider: str,
        config: Dict[str, Any],
        use_cache: bool = True
    ) -> Optional[AIService]:
        """
        Create and initialize a service instance.

        This is a convenience method that creates a service and calls
        its initialize() method.

        Args:
            service_type: Type of AI service
            provider: Provider name
            config: Configuration dictionary
            use_cache: If True, return cached instance if available

        Returns:
            Initialized service instance, or None if initialization failed

        Example:
            >>> service = await AIServiceFactory.create_and_initialize_service(
            ...     ServiceType.EMBEDDING,
            ...     "openai",
            ...     config
            ... )
        """
        try:
            service = cls.create_service(service_type, provider, config, use_cache)

            if await service.initialize():
                return service
            else:
                logger.error(
                    f"Failed to initialize {service_type.value} service "
                    f"with provider {provider}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error creating/initializing {service_type.value} service "
                f"with provider {provider}: {str(e)}"
            )
            return None

    @classmethod
    def get_cached_service(
        cls,
        service_type: ServiceType,
        provider: str
    ) -> Optional[AIService]:
        """
        Get a cached service instance.

        Args:
            service_type: Type of AI service
            provider: Provider name

        Returns:
            Cached service instance, or None if not cached
        """
        key = (service_type, provider)
        return cls._service_cache.get(key)

    @classmethod
    def clear_cache(
        cls,
        service_type: Optional[ServiceType] = None,
        provider: Optional[str] = None
    ) -> None:
        """
        Clear cached service instances.

        Args:
            service_type: If provided, only clear this service type
            provider: If provided, only clear this provider

        Example:
            >>> # Clear all cache
            >>> AIServiceFactory.clear_cache()
            >>>
            >>> # Clear only embedding services
            >>> AIServiceFactory.clear_cache(service_type=ServiceType.EMBEDDING)
            >>>
            >>> # Clear only OpenAI services
            >>> AIServiceFactory.clear_cache(provider="openai")
        """
        if service_type is None and provider is None:
            # Clear all
            cls._service_cache.clear()
            logger.debug("Cleared all cached services")
        else:
            # Clear selectively
            keys_to_remove = []
            for key in cls._service_cache:
                svc_type, svc_provider = key
                if (service_type is None or svc_type == service_type) and \
                   (provider is None or svc_provider == provider):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del cls._service_cache[key]

            logger.debug(f"Cleared {len(keys_to_remove)} cached services")

    @classmethod
    async def close_all_services(cls) -> None:
        """
        Close all cached service instances.

        This should be called on application shutdown to ensure
        proper cleanup of resources.
        """
        logger.info(f"Closing {len(cls._service_cache)} cached services")

        for service in cls._service_cache.values():
            try:
                await service.close()
            except Exception as e:
                logger.error(f"Error closing service {service.__class__.__name__}: {str(e)}")

        cls._service_cache.clear()
        logger.info("All services closed")

    @classmethod
    def is_service_registered(
        cls,
        service_type: ServiceType,
        provider: str
    ) -> bool:
        """
        Check if a service is registered.

        Args:
            service_type: Type of AI service
            provider: Provider name

        Returns:
            True if registered, False otherwise
        """
        key = (service_type, provider)
        return key in cls._service_registry

    @classmethod
    def list_available_services(cls) -> Dict[str, list]:
        """
        List all available services grouped by service type.

        Returns:
            Dictionary mapping service types to lists of providers

        Example:
            >>> AIServiceFactory.list_available_services()
            {
                'embedding': ['openai', 'anthropic', 'ollama', 'cohere'],
                'inference': ['openai', 'anthropic', 'ollama'],
                'moderation': ['openai', 'anthropic'],
                ...
            }
        """
        services: Dict[str, list] = {}

        for service_type, provider in cls._service_registry.keys():
            type_name = service_type.value
            if type_name not in services:
                services[type_name] = []
            services[type_name].append(provider)

        return services

    @classmethod
    def get_service_class(
        cls,
        service_type: ServiceType,
        provider: str
    ) -> Optional[Type[AIService]]:
        """
        Get the service class for a given type/provider.

        Args:
            service_type: Type of AI service
            provider: Provider name

        Returns:
            Service class or None if not registered
        """
        key = (service_type, provider)
        return cls._service_registry.get(key)

    @classmethod
    def unregister_service(
        cls,
        service_type: ServiceType,
        provider: str
    ) -> bool:
        """
        Unregister a service.

        Args:
            service_type: Type of AI service
            provider: Provider name

        Returns:
            True if service was unregistered, False if it wasn't registered
        """
        key = (service_type, provider)

        if key in cls._service_registry:
            del cls._service_registry[key]
            logger.debug(
                f"Unregistered {service_type.value} service with provider {provider}"
            )
            return True

        return False
