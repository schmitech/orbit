"""
OpenRouter Provider for Pipeline Architecture

This module provides a clean OpenRouter implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class OpenRouterProvider(LLMProvider):
    """
    Clean OpenRouter implementation for the pipeline architecture.
    
    This provider communicates directly with OpenRouter's API using the OpenAI client
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenRouter provider.
        
        Args:
            config: Configuration dictionary containing OpenRouter settings
        """
        self.config = config
        openrouter_config = config.get("inference", {}).get("openrouter", {})
        
        self.api_key = openrouter_config.get("api_key")
        self.base_url = openrouter_config.get("base_url", "https://openrouter.ai/api/v1")
        self.model = openrouter_config.get("model", "openai/gpt-4o")
        self.temperature = openrouter_config.get("temperature", 0.1)
        self.top_p = openrouter_config.get("top_p", 0.8)
        self.max_tokens = openrouter_config.get("max_tokens", 1024)
        self.stream = openrouter_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the OpenRouter client."""
        try:
            from openai import AsyncOpenAI
            
            if not self.api_key:
                raise ValueError("OpenRouter API key is required")
            
            # OpenRouter is compatible with OpenAI client
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            
            self.logger.info(f"Initialized OpenRouter provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("openai package not installed. Please install with: pip install openai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenRouter client: {str(e)}")
            raise
    
    def _build_messages(self, prompt: str) -> list:
        """
        Build messages in the format expected by OpenRouter.
        
        Args:
            prompt: The input prompt
            
        Returns:
            List of message dictionaries
        """
        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                messages = []
                if system_part:
                    messages.append({"role": "system", "content": system_part})
                messages.append({"role": "user", "content": user_part})
                return messages
        
        # If no clear separation, treat entire prompt as user message
        return [{"role": "user", "content": prompt}]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using OpenRouter.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Generating with OpenRouter: model={self.model}, temperature={self.temperature}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_completion_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Error generating response with OpenRouter: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using OpenRouter.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with OpenRouter")
            
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_completion_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=True,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens", "stream"]}
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with OpenRouter: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the OpenRouter client."""
        if self.client and hasattr(self.client, "close"):
            try:
                await self.client.close()
                self.logger.info("OpenRouter provider closed")
            except Exception as e:
                self.logger.error(f"Error closing OpenRouter client: {str(e)}")
        self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the OpenRouter configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("OpenRouter API key is missing")
                return False
            
            if not self.model:
                self.logger.error("OpenRouter model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_completion_tokens=5,
                temperature=0
            )
            
            if self.verbose:
                self.logger.info("OpenRouter configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("openai package not installed")
            return False
        except Exception as e:
            self.logger.error(f"OpenRouter configuration validation failed: {str(e)}")
            return False