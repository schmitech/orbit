"""
Base classes for content moderation providers.
"""

import logging
import abc
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Union, Type
import time

# Configure logging
logger = logging.getLogger(__name__)

class ModerationCategory(Enum):
    """Categories for content moderation"""
    HATE = auto()
    HARASSMENT = auto()
    SEXUAL = auto()
    SEXUAL_MINORS = auto()
    VIOLENCE = auto()
    SELF_HARM = auto()
    EXPLICIT = auto()
    ILLICIT = auto()
    PROHIBITED = auto()
    OTHER = auto()

class ModerationResult:
    """Result of a moderation check"""
    def __init__(
        self, 
        is_flagged: bool = False, 
        categories: Dict[str, float] = None,
        provider: str = None,
        model: str = None,
        error: Optional[str] = None
    ):
        self.is_flagged = is_flagged
        self.categories = categories or {}
        self.provider = provider
        self.model = model
        self.error = error
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the result to a dictionary"""
        return {
            "is_flagged": self.is_flagged,
            "categories": self.categories,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
            "timestamp": self.timestamp
        }

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
    """
    
    _registry = {}
    
    @classmethod
    def register(cls, provider_name: str, moderator_class: Type[ModeratorService]) -> None:
        """
        Register a moderator class for a provider.
        
        Args:
            provider_name: The name of the provider (e.g., 'openai', 'anthropic')
            moderator_class: The moderator class to use for this provider
        """
        cls._registry[provider_name] = moderator_class
    
    @classmethod
    def create_moderator(cls, config: Dict[str, Any], provider_name: str = None) -> ModeratorService:
        """
        Create a moderator service instance for the specified provider.
        
        Args:
            config: Configuration dictionary
            provider_name: The name of the provider to use, or None to use the configured default
            
        Returns:
            An instance of the appropriate moderator service
            
        Raises:
            ValueError: If the specified provider is not supported
        """
        if provider_name is None:
            # Get provider from safety configuration
            provider_name = config.get('safety', {}).get('moderator')
            if not provider_name:
                provider_name = config.get('general', {}).get('inference_provider', 'openai')
        
        # Check if we have a registered handler for this provider
        if provider_name not in cls._registry:
            logger.error(f"No moderator registered for provider '{provider_name}'")
            raise ValueError(f"Unsupported moderation provider: {provider_name}")
        
        # Create and return the moderator instance
        moderator_class = cls._registry[provider_name]
        logger.info(f"Creating {provider_name} moderator using {moderator_class.__name__}")
        return moderator_class(config) 