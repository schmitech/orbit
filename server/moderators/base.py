"""
Base classes for content moderation providers.

DEPRECATED: This module is maintained for backward compatibility only.
Please use ai_services.services.moderation_service instead.
"""

import logging
import abc
from typing import Dict, Any, List, Optional, Union, Type

# Import from new location for backward compatibility
from ai_services.services.moderation_service import (
    ModerationCategory,
    ModerationResult
)

# Configure logging
logger = logging.getLogger(__name__)

# Log deprecation warning
logger.warning(
    "moderators.base is deprecated. Please use ai_services.services.moderation_service instead."
)

class ModeratorService(abc.ABC):
    """
    Base class for content moderation services.
    
    This abstract class defines the interface that all moderation services
    must implement, regardless of the underlying provider.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the moderation service with configuration.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.initialized = False
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abc.abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the moderation service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate a single content item.
        
        Args:
            content: The text content to moderate
            
        Returns:
            ModerationResult with the moderation outcome
        """
        pass
    
    async def moderate_batch(self, contents: List[str]) -> List[ModerationResult]:
        """
        Moderate multiple content items in a batch.
        
        Default implementation calls moderate_content for each item.
        Subclasses should override this if they support native batching.
        
        Args:
            contents: List of text content to moderate
            
        Returns:
            List of ModerationResult objects
        """
        results = []
        for content in contents:
            result = await self.moderate_content(content)
            results.append(result)
        return results
    
    @abc.abstractmethod
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the moderation service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        pass
    
    @abc.abstractmethod
    async def close(self) -> None:
        """
        Close the moderation service and release any resources.
        """
        pass

class ModeratorFactory:
    """
    Factory for creating moderation service instances based on provider.

    DEPRECATED: This factory is maintained for backward compatibility only.
    Please use AIServiceFactory from ai_services.factory instead.
    """

    _registry = {}

    @classmethod
    def register(cls, provider_name: str, moderator_class: Type[ModeratorService]) -> None:
        """
        Register a moderator class for a provider.

        DEPRECATED: Use AIServiceFactory.register_service() instead.

        Args:
            provider_name: The name of the provider (e.g., 'openai', 'anthropic')
            moderator_class: The moderator class to use for this provider
        """
        logger.warning(
            f"ModeratorFactory.register() is deprecated. "
            f"Use AIServiceFactory.register_service() instead."
        )
        cls._registry[provider_name] = moderator_class

    @classmethod
    def create_moderator(cls, config: Dict[str, Any], provider_name: str = None) -> 'ModeratorService':
        """
        Create a moderator service instance for the specified provider.

        DEPRECATED: Use AIServiceFactory.create_service() instead.

        Args:
            config: Configuration dictionary
            provider_name: The name of the provider to use, or None to use the configured default

        Returns:
            An instance of the appropriate moderator service

        Raises:
            ValueError: If the specified provider is not supported
        """
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType

        logger.warning(
            f"ModeratorFactory.create_moderator() is deprecated. "
            f"Use AIServiceFactory.create_service() instead."
        )

        if provider_name is None:
            # Get provider from safety configuration
            provider_name = config.get('safety', {}).get('moderator')
            if not provider_name:
                provider_name = config.get('general', {}).get('inference_provider', 'openai')

        try:
            # Redirect to new factory
            return AIServiceFactory.create_service(
                ServiceType.MODERATION,
                provider_name,
                config
            )
        except ValueError:
            # Fallback to old registry if available
            if provider_name in cls._registry:
                moderator_class = cls._registry[provider_name]
                logger.info(f"Creating {provider_name} moderator using legacy registry: {moderator_class.__name__}")
                return moderator_class(config)

            # Neither new nor old factory has this provider
            logger.error(f"No moderator registered for provider '{provider_name}'")
            raise ValueError(f"Unsupported moderation provider: {provider_name}") 