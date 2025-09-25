"""
OpenAI Provider for Pipeline Architecture

This module provides a clean OpenAI implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from openai import AsyncOpenAI
from .llm_provider import LLMProvider

class OpenAIProvider(LLMProvider):
    """
    Clean OpenAI implementation for the pipeline architecture.
    
    This provider communicates directly with OpenAI's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI provider.
        
        Args:
            config: Configuration dictionary containing OpenAI settings
        """
        self.config = config
        self.api_key = config["inference"]["openai"]["api_key"]
        self.model = config["inference"]["openai"]["model"]
        self.temperature = config["inference"]["openai"].get("temperature", 0.1)
        self.max_tokens = config["inference"]["openai"].get("max_tokens", 2000)
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.logger.info(f"Initialized OpenAI provider with model: {self.model}")
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using new API
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_completion_tokens": self.max_tokens,
                **kwargs
            }

            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Error generating response with OpenAI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using new API
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_completion_tokens": self.max_tokens,
                "stream": True,
                **kwargs
            }

            stream = await self.client.chat.completions.create(**params)
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with OpenAI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the OpenAI client."""
        if self.client:
            await self.client.close()
            self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the OpenAI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("OpenAI API key is missing")
                return False
            
            if not self.model:
                self.logger.error("OpenAI model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Try a simple test request using new API
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_completion_tokens=5
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"OpenAI configuration validation failed: {str(e)}")
            return False 