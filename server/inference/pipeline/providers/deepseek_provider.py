"""
DeepSeek Provider for Pipeline Architecture

This module provides a clean DeepSeek implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class DeepSeekProvider(LLMProvider):
    """
    Clean DeepSeek implementation for the pipeline architecture.
    
    This provider communicates directly with DeepSeek's API using the OpenAI-compatible interface
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the DeepSeek provider.
        
        Args:
            config: Configuration dictionary containing DeepSeek settings
        """
        self.config = config
        deepseek_config = config.get("inference", {}).get("deepseek", {})
        
        self.api_key = deepseek_config.get("api_key")
        self.api_base = deepseek_config.get("api_base", "https://api.deepseek.com/v1")
        self.model = deepseek_config.get("model", "deepseek-chat")
        self.temperature = deepseek_config.get("temperature", 0.1)
        self.top_p = deepseek_config.get("top_p", 0.8)
        self.max_tokens = deepseek_config.get("max_tokens", 1024)
        self.stream = deepseek_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the DeepSeek client."""
        try:
            from openai import AsyncOpenAI
            
            if not self.api_key:
                raise ValueError("DeepSeek API key is required")
            
            # DeepSeek API is compatible with OpenAI client
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            self.logger.info(f"Initialized DeepSeek provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("openai package not installed. Please install with: pip install openai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize DeepSeek client: {str(e)}")
            raise
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using DeepSeek.
        
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
                self.logger.debug(f"Sending request to DeepSeek: model={self.model}, temperature={self.temperature}")
            
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
            self.logger.error(f"Error generating response with DeepSeek: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using DeepSeek.
        
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
                self.logger.debug(f"Starting streaming request to DeepSeek: model={self.model}")
            
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
            self.logger.error(f"Error generating streaming response with DeepSeek: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the DeepSeek client."""
        if self.client and hasattr(self.client, "close"):
            try:
                await self.client.close()
                self.logger.info("DeepSeek provider closed")
            except Exception as e:
                self.logger.error(f"Error closing DeepSeek client: {str(e)}")
        self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the DeepSeek configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("DeepSeek API key is missing")
                return False
            
            if not self.model:
                self.logger.error("DeepSeek model is missing")
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
                self.logger.info("DeepSeek configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("openai package not installed")
            return False
        except Exception as e:
            self.logger.error(f"DeepSeek configuration validation failed: {str(e)}")
            return False