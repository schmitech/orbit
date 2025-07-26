"""
Mistral AI Provider for Pipeline Architecture

This module provides a clean Mistral AI implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class MistralProvider(LLMProvider):
    """
    Clean Mistral AI implementation for the pipeline architecture.
    
    This provider communicates directly with Mistral's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Mistral provider.
        
        Args:
            config: Configuration dictionary containing Mistral settings
        """
        self.config = config
        mistral_config = config.get("inference", {}).get("mistral", {})
        
        self.api_key = mistral_config.get("api_key")
        self.api_base = mistral_config.get("api_base", "https://api.mistral.ai/v1")
        self.model = mistral_config.get("model", "mistral-small-latest")
        self.temperature = mistral_config.get("temperature", 0.1)
        self.top_p = mistral_config.get("top_p", 0.8)
        self.max_tokens = mistral_config.get("max_tokens", 1024)
        self.stream = mistral_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Mistral client."""
        try:
            from mistralai import Mistral
            
            if not self.api_key:
                raise ValueError("Mistral API key is required")
            
            self.client = Mistral(api_key=self.api_key)
            self.logger.info(f"Initialized Mistral provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("mistralai package not installed. Please install with: pip install mistralai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Mistral client: {str(e)}")
            raise
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Mistral AI.
        
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
                self.logger.debug(f"Sending request to Mistral: model={self.model}, temperature={self.temperature}")
            
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Error generating response with Mistral: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Mistral AI.
        
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
                self.logger.debug(f"Starting streaming request to Mistral: model={self.model}")
            
            stream = await self.client.chat.stream_async(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            async for chunk in stream:
                if chunk.data.choices and chunk.data.choices[0].delta.content:
                    yield chunk.data.choices[0].delta.content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Mistral: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Mistral client."""
        # The Mistral client doesn't require explicit cleanup
        self.client = None
        self.logger.info("Mistral provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Mistral configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Mistral API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Mistral model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
                temperature=0
            )
            
            if self.verbose:
                self.logger.info("Mistral configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("mistralai package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Mistral configuration validation failed: {str(e)}")
            return False