"""
Unified Provider Adapter

This adapter bridges the new unified AI services architecture with the
existing pipeline LLMProvider interface, allowing the pipeline to use
the new services without breaking changes.
"""

from typing import Dict, Any, AsyncGenerator, Optional
from .llm_provider import LLMProvider

# Import the new unified architecture
from server.ai_services import AIServiceFactory, ServiceType, register_all_services
from server.ai_services.base import AIService


class UnifiedProviderAdapter(LLMProvider):
    """
    Adapter that wraps new unified AI services to provide the LLMProvider interface.

    This allows the pipeline to use the new architecture transparently.
    """

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the adapter with a provider from the new architecture.

        Args:
            config: Application configuration
            provider_name: Name of the provider (e.g., 'openai', 'anthropic', 'ollama')
        """
        self.config = config
        self.provider_name = provider_name
        self.service: Optional[AIService] = None

        # Ensure all services are registered
        register_all_services()

    async def initialize(self, clock_service: Optional[Any] = None) -> None:
        """Initialize the underlying AI service."""
        # Create the service using the new factory
        self.service = AIServiceFactory.create_service(
            ServiceType.INFERENCE,
            self.provider_name,
            self.config
        )

        # Initialize the service
        await self.service.initialize()

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using the new AI service.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated response text
        """
        if not self.service:
            raise RuntimeError("Provider not initialized. Call initialize() first.")

        return await self.service.generate(prompt, **kwargs)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using the new AI service.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters

        Yields:
            Response chunks as they are generated
        """
        if not self.service:
            raise RuntimeError("Provider not initialized. Call initialize() first.")

        async for chunk in self.service.generate_stream(prompt, **kwargs):
            yield chunk

    async def close(self) -> None:
        """Clean up resources."""
        if self.service:
            await self.service.close()

    async def validate_config(self) -> bool:
        """
        Validate provider configuration.

        Returns:
            True if configuration is valid
        """
        try:
            # Check if service can be created
            if not self.service:
                test_service = AIServiceFactory.create_service(
                    ServiceType.INFERENCE,
                    self.provider_name,
                    self.config
                )
                return test_service is not None
            return True
        except Exception:
            return False


def create_unified_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """
    Factory function to create a provider using the new unified architecture.

    Args:
        provider_name: Name of the provider
        config: Application configuration

    Returns:
        LLMProvider instance wrapping the new architecture

    Example:
        >>> provider = create_unified_provider('openai', config)
        >>> await provider.initialize()
        >>> response = await provider.generate("Hello, how are you?")
    """
    return UnifiedProviderAdapter(config, provider_name)
