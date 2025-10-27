"""
LLM Provider Base Class

This module defines the base interface for LLM providers in the pipeline architecture.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers in the pipeline architecture.
    
    This interface is maintained for backward compatibility with the existing
    pipeline while the underlying implementation uses the new unified AI services.
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
