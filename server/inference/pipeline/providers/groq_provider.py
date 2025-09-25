"""
Groq Provider for Pipeline Architecture

This module provides a clean Groq implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class GroqProvider(LLMProvider):
    """
    Clean Groq implementation for the pipeline architecture.
    
    This provider communicates directly with Groq's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Groq provider.
        
        Args:
            config: Configuration dictionary containing Groq settings
        """
        self.config = config
        groq_config = config.get("inference", {}).get("groq", {})
        
        self.api_key = groq_config.get("api_key")
        self.model = groq_config.get("model", "llama3-8b-8192")
        self.temperature = groq_config.get("temperature", 0.1)
        self.top_p = groq_config.get("top_p", 0.8)
        self.max_tokens = groq_config.get("max_tokens", 1024)
        self.stream = groq_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Groq client."""
        try:
            from groq import AsyncGroq
            
            if not self.api_key:
                raise ValueError("Groq API key is required")
            
            self.client = AsyncGroq(api_key=self.api_key)
            self.logger.info(f"Initialized Groq provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("groq package not installed. Please install with: pip install groq")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Groq client: {str(e)}")
            raise
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Groq.

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
                # Traditional format - try to extract system prompt
                messages = [{"role": "user", "content": prompt}]

                # Extract system prompt if present in the prompt
                if "\nUser:" in prompt and "Assistant:" in prompt:
                    # Split to extract system prompt
                    parts = prompt.split("\nUser:", 1)
                    if len(parts) == 2:
                        system_part = parts[0].strip()
                        user_part = parts[1].replace("Assistant:", "").strip()
                        messages = [
                            {"role": "system", "content": system_part},
                            {"role": "user", "content": user_part}
                        ]
            
            if self.verbose:
                self.logger.debug(f"Sending request to Groq: model={self.model}, temperature={self.temperature}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Error generating response with Groq: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Groq.

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
                # Traditional format - try to extract system prompt
                messages = [{"role": "user", "content": prompt}]

                # Extract system prompt if present
                if "\nUser:" in prompt and "Assistant:" in prompt:
                    parts = prompt.split("\nUser:", 1)
                    if len(parts) == 2:
                        system_part = parts[0].strip()
                        user_part = parts[1].replace("Assistant:", "").strip()
                        messages = [
                        {"role": "system", "content": system_part},
                        {"role": "user", "content": user_part}
                    ]
            
            if self.verbose:
                self.logger.debug(f"Starting streaming request to Groq: model={self.model}")
            
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=True,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens", "stream"]}
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Groq: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Groq client."""
        if self.client and hasattr(self.client, "close"):
            try:
                await self.client.close()
                self.logger.info("Groq provider closed")
            except Exception as e:
                self.logger.error(f"Error closing Groq client: {str(e)}")
        self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the Groq configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Groq API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Groq model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
                temperature=0
            )
            
            if self.verbose:
                self.logger.info("Groq configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("groq package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Groq configuration validation failed: {str(e)}")
            return False