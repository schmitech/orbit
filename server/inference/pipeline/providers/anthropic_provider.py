"""
Anthropic Provider for Pipeline Architecture

This module provides a clean Anthropic implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
import anthropic
from .llm_provider import LLMProvider

class AnthropicProvider(LLMProvider):
    """
    Clean Anthropic implementation for the pipeline architecture.
    
    This provider communicates directly with Anthropic's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic provider.
        
        Args:
            config: Configuration dictionary containing Anthropic settings
        """
        self.config = config
        self.api_key = config["inference"]["anthropic"]["api_key"]
        self.model = config["inference"]["anthropic"]["model"]
        self.max_tokens = config["inference"]["anthropic"].get("max_tokens", 2000)
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self) -> None:
        """Initialize the Anthropic client."""
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        self.logger.info(f"Initialized Anthropic provider with model: {self.model}")
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Anthropic.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Error generating response with Anthropic: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Anthropic.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()
        
        try:
            stream = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                **kwargs
            )
            
            async with stream as response:
                async for chunk in response:
                    if chunk.type == "content_block_delta":
                        yield chunk.delta.text
                        
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Anthropic: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Anthropic client."""
        if self.client:
            await self.client.close()
            self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the Anthropic configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Anthropic API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Anthropic model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Try a simple test request
            await self.client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "test"}]
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Anthropic configuration validation failed: {str(e)}")
            return False 