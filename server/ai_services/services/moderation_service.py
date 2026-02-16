"""
Moderation service interface and base implementations.

This module defines the common interface for all content moderation services,
providing a unified API regardless of the underlying provider.

Supported providers return various category taxonomies:
- OpenAI: harassment, hate, illicit, self_harm, sexual, violence (with subcategories)
- Llama Guard 3: MLCommons taxonomy (violent_crimes, non_violent_crimes, etc.)
- Anthropic: Combined taxonomy matching Llama Guard 3 categories
"""

from abc import abstractmethod
from typing import Dict, Any, List, Optional
import time

from ..base import ProviderAIService, ServiceType


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


class ModerationService(ProviderAIService):
    """
    Base class for all content moderation services.

    This class defines the common interface that all moderation service
    implementations must follow, regardless of provider (OpenAI, Anthropic,
    Ollama, etc.).

    Key Methods:
        - moderate_content: Moderate a single content item
        - moderate_batch: Moderate multiple content items

    Configuration Support:
        - Configurable endpoints via config
        - Model configuration
        - Category thresholds
    """

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the moderation service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'openai', 'anthropic')
        """
        super().__init__(config, ServiceType.MODERATION, provider_name)

    @abstractmethod
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate a single content item.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult with the moderation outcome

        Example:
            >>> service = OpenAIModerationService(config)
            >>> await service.initialize()
            >>> result = await service.moderate_content("Some text")
            >>> print(result.is_flagged)
            False
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

        Example:
            >>> service = OpenAIModerationService(config)
            >>> await service.initialize()
            >>> results = await service.moderate_batch(["Text 1", "Text 2"])
            >>> len(results)
            2
        """
        results = []
        for content in contents:
            result = await self.moderate_content(content)
            results.append(result)
        return results


# Helper function for service creation
def create_moderation_service(
    provider: str,
    config: Dict[str, Any]
) -> ModerationService:
    """
    Factory function to create a moderation service.

    Args:
        provider: Provider name (e.g., 'openai', 'anthropic')
        config: Configuration dictionary

    Returns:
        Moderation service instance

    Example:
        >>> service = create_moderation_service('openai', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.MODERATION,
        provider,
        config
    )
