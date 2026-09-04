"""
LLM Provider Base Class

This module defines the base interface for LLM providers in the pipeline architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from collections.abc import AsyncGenerator


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers in the pipeline architecture.
    """

    @abstractmethod
    async def initialize(self, clock_service: Optional[Any] = None) -> None:
        """
        Initialize the provider.
        
        Args:
            clock_service: Optional clock service for time-based operations
        """
        pass

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate a response for the given prompt.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            Generated response text
        """
        pass

    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for the given prompt.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        pass

    async def generate_tracked(
        self,
        prompt: str,
        usage_sink: Optional[dict[str, Any]] = None,
        cache_prefix_len: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Same as generate(), but fills usage_sink with token usage / applies a
        prompt-caching breakpoint when the underlying service supports them.
        Non-abstract with a plain delegation default (both extra kwargs
        dropped) so legacy provider implementations and test doubles that
        only implement generate() keep working unchanged.
        """
        return await self.generate(prompt, **kwargs)

    async def generate_stream_tracked(
        self,
        prompt: str,
        usage_sink: Optional[dict[str, Any]] = None,
        cache_prefix_len: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Streaming counterpart of generate_tracked()."""
        async for chunk in self.generate_stream(prompt, **kwargs):
            yield chunk

    async def generate_with_tools(self, messages: Any, tools: Any, **kwargs) -> Any:
        """
        Single round of tool-enabled generation. Non-abstract with a raising
        default — most LLMProvider implementations don't support native tool
        calling; concrete providers that do (UnifiedProviderAdapter) override it.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_with_tools."
        )

    async def generate_with_tools_tracked(
        self,
        messages: Any,
        tools: Any,
        usage_sink: Optional[dict[str, Any]] = None,
        cache_prefix_len: Optional[int] = None,
        **kwargs,
    ) -> Any:
        """
        Same as generate_with_tools(), but fills usage_sink with token usage /
        applies a prompt-caching breakpoint when the underlying service
        supports them. Non-abstract with a plain delegation default (both
        extra kwargs dropped) so legacy providers and test doubles that only
        implement generate_with_tools() keep working unchanged.
        """
        return await self.generate_with_tools(messages, tools, **kwargs)

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

    @abstractmethod
    async def validate_config(self) -> bool:
        """
        Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        pass
