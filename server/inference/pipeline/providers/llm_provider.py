"""
LLM Provider Interface

This module defines the interface for LLM providers in the pipeline architecture.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional

class LLMProvider(ABC):
    """
    Simple interface for LLM providers - only handles generation.
    
    This interface is designed to be minimal and focused, handling only
    the core inference functionality without the complexity of the legacy
    LLM client architecture.
    """
    
    @abstractmethod
    async def initialize(self, clock_service: Optional[Any] = None) -> None:
        """Initialize the LLM provider."""
        pass
    
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response for the given prompt.
        
        Args:
            prompt: The input prompt.
            **kwargs: Additional generation parameters, including an optional
                      'messages' list for structured conversations.
            
        Returns:
            The generated response text
        """
        pass
    
    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response.
        
        Args:
            prompt: The input prompt.
            **kwargs: Additional generation parameters, including an optional
                      'messages' list for structured conversations.
            
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
            True if configuration is valid, False otherwise
        """
        pass