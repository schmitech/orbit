"""
xAI Provider for Pipeline Architecture

This module provides a clean xAI implementation for the pipeline architecture.
"""

import json
import re
import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class XAIProvider(LLMProvider):
    """
    Clean xAI implementation for the pipeline architecture.
    
    This provider communicates directly with xAI's API using aiohttp
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the xAI provider.
        
        Args:
            config: Configuration dictionary containing xAI settings
        """
        self.config = config
        xai_config = config.get("inference", {}).get("xai", {})
        
        self.api_key = xai_config.get("api_key")
        self.api_base = xai_config.get("api_base", "https://api.x.ai/v1")
        self.model = xai_config.get("model", "grok-3-mini-beta")
        self.temperature = xai_config.get("temperature", 0.1)
        self.top_p = xai_config.get("top_p", 0.8)
        self.max_tokens = xai_config.get("max_tokens", 1024)
        self.stream = xai_config.get("stream", True)
        self.show_thinking = xai_config.get("show_thinking", False)
        
        self.session = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the xAI provider."""
        try:
            import aiohttp
            
            if not self.api_key:
                raise ValueError("xAI API key is required")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            self.session = aiohttp.ClientSession(headers=headers)
            
            self.logger.info(f"Initialized xAI provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("aiohttp package not installed. Please install with: pip install aiohttp")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize xAI client: {str(e)}")
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
    
    def _build_messages(self, prompt: str) -> list:
        """
        Build messages in the format expected by xAI.
        
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
        Generate response using xAI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.session:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Generating with xAI: model={self.model}, temperature={self.temperature}")
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "top_p": kwargs.get("top_p", self.top_p),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "stream": False,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            }
            
            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"xAI API error: {error_text}")
                
                data = await response.json()
            
            # Extract response text
            response_text = data["choices"][0]["message"]["content"]
            
            # Clean up the response
            response_text = self._clean_response_text(response_text)
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with xAI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using xAI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.session:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with xAI")
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "top_p": kwargs.get("top_p", self.top_p),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "stream": True,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens", "stream"]}
            }
            
            current_chunk = ""
            in_thinking_block = False
            
            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"xAI API error: {error_text}")
                
                async for line in response.content:
                    chunk = line.decode().strip()
                    if not chunk or not chunk.startswith("data:"):
                        continue
                    
                    data = chunk[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    
                    try:
                        payload_data = json.loads(data)
                        delta = payload_data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
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
                                    
                    except json.JSONDecodeError:
                        continue
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with xAI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the xAI provider."""
        if self.session:
            try:
                await self.session.close()
                self.logger.info("xAI provider closed")
            except Exception as e:
                self.logger.error(f"Error closing xAI client: {str(e)}")
        self.session = None
    
    async def validate_config(self) -> bool:
        """
        Validate the xAI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("xAI API key is missing")
                return False
            
            if not self.model:
                self.logger.error("xAI model is missing")
                return False
            
            # Test connection with a simple request
            if not self.session:
                await self.initialize()
            
            # Validate with a minimal test
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
                "temperature": 0,
                "stream": False
            }
            
            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"xAI validation failed: {error_text}")
                    return False
            
            if self.verbose:
                self.logger.info("xAI configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("aiohttp package not installed")
            return False
        except Exception as e:
            self.logger.error(f"xAI configuration validation failed: {str(e)}")
            return False