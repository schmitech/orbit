"""
Together AI Provider for Pipeline Architecture

This module provides a clean Together AI implementation for the pipeline architecture.
"""

import logging
import re
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class TogetherProvider(LLMProvider):
    """
    Clean Together AI implementation for the pipeline architecture.
    
    This provider communicates directly with Together AI's API using their official SDK
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Together AI provider.
        
        Args:
            config: Configuration dictionary containing Together AI settings
        """
        self.config = config
        together_config = config.get("inference", {}).get("together", {})
        
        self.api_key = together_config.get("api_key")
        self.api_base = together_config.get("api_base", "https://api.together.xyz/v1")
        self.model = together_config.get("model", "meta-llama/Llama-2-7b-chat-hf")
        self.temperature = together_config.get("temperature", 0.1)
        self.top_p = together_config.get("top_p", 0.8)
        self.max_tokens = together_config.get("max_tokens", 1024)
        self.stream = together_config.get("stream", True)
        self.show_thinking = together_config.get("show_thinking", False)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Together AI client."""
        try:
            from together import AsyncTogether
            
            if not self.api_key:
                raise ValueError("Together AI API key is required")
            
            self.client = AsyncTogether(
                api_key=self.api_key,
                base_url=self.api_base
            )
            
            self.logger.info(f"Initialized Together AI provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("together package not installed. Please install with: pip install together")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Together AI client: {str(e)}")
            raise
    
    def _clean_response_text(self, text: str) -> str:
        """
        Remove thinking process from response if show_thinking is False.
        
        Args:
            text: Raw response text from the model
            
        Returns:
            Cleaned response text
        """
        if not self.show_thinking:
            # Remove content between <think> tags
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            # Clean up any extra whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = text.strip()
            # Remove any remaining thinking tags
            text = text.replace('<think>', '').replace('</think>', '')
        return text
    
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Together AI.
        
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
            
            if self.verbose:
                self.logger.debug(f"Generating with Together AI: model={self.model}, temperature={self.temperature}")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            # Extract response text
            response_text = response.choices[0].message.content
            
            # Clean up the response
            response_text = self._clean_response_text(response_text)
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with Together AI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Together AI.
        
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
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Together AI")
            
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=True,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens", "stream"]}
            )
            
            current_chunk = ""
            in_thinking_block = False
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    current_chunk += content
                    
                    # Check if we're entering or exiting a thinking block
                    if '<think>' in content:
                        in_thinking_block = True
                    if '</think>' in content:
                        in_thinking_block = False
                        continue
                        
                    # Only yield content if we're not in a thinking block or show_thinking is True
                    if self.show_thinking or not in_thinking_block:
                        if content:
                            yield content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Together AI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Together AI client."""
        if self.client and hasattr(self.client, "close"):
            try:
                await self.client.close()
                self.logger.info("Together AI provider closed")
            except Exception as e:
                self.logger.error(f"Error closing Together AI client: {str(e)}")
        self.client = None
    
    async def validate_config(self) -> bool:
        """
        Validate the Together AI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Together AI API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Together AI model is missing")
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
            
            if not response or not response.choices:
                self.logger.error("No response received from Together AI")
                return False
            
            if self.verbose:
                self.logger.info("Together AI configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("together package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Together AI configuration validation failed: {str(e)}")
            return False