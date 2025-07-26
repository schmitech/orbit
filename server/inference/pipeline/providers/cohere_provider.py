"""
Cohere Provider for Pipeline Architecture

This module provides a clean Cohere implementation for the pipeline architecture.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class CohereProvider(LLMProvider):
    """
    Clean Cohere implementation for the pipeline architecture.
    
    This provider communicates directly with Cohere's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Cohere provider.
        
        Args:
            config: Configuration dictionary containing Cohere settings
        """
        self.config = config
        cohere_config = config.get("inference", {}).get("cohere", {})
        
        self.api_key = cohere_config.get("api_key")
        self.api_base = cohere_config.get("api_base", "https://api.cohere.ai/v2")
        self.model = cohere_config.get("model", "command-r7b-12-2024")
        self.temperature = cohere_config.get("temperature", 0.1)
        self.top_p = cohere_config.get("top_p", 0.8)
        self.max_tokens = cohere_config.get("max_tokens", 1024)
        self.stream = cohere_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Cohere client."""
        try:
            import cohere
            
            if not self.api_key:
                raise ValueError("Cohere API key is required")
            
            # Use ClientV2 for the latest API
            self.client = cohere.ClientV2(api_key=self.api_key)
            self.logger.info(f"Initialized Cohere provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("cohere package not installed. Please install with: pip install cohere")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Cohere client: {str(e)}")
            raise
    
    def _build_messages(self, prompt: str) -> list:
        """
        Build messages in the format expected by Cohere.
        
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
        Generate response using Cohere.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Sending request to Cohere: model={self.model}, temperature={self.temperature}")
            
            # Prepare parameters (Cohere uses 'p' instead of 'top_p')
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "p": kwargs.get("top_p", self.top_p),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            }
            
            # Add any additional parameters
            for key, value in kwargs.items():
                if key not in ["temperature", "top_p", "max_tokens"]:
                    params[key] = value
            
            # Use asyncio.to_thread since Cohere client is synchronous
            response = await asyncio.to_thread(self.client.chat, **params)
            
            # Extract text from response
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                if response.message.content and len(response.message.content) > 0:
                    return response.message.content[0].text
            
            # Fallback response parsing
            if hasattr(response, 'text'):
                return response.text
            
            self.logger.error(f"Unexpected Cohere response format: {response}")
            raise ValueError("Could not extract text from Cohere response")
            
        except Exception as e:
            self.logger.error(f"Error generating response with Cohere: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Cohere.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming request to Cohere: model={self.model}")
            
            # Prepare parameters
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "p": kwargs.get("top_p", self.top_p),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            }
            
            # Add any additional parameters
            for key, value in kwargs.items():
                if key not in ["temperature", "top_p", "max_tokens"]:
                    params[key] = value
            
            # Generate streaming response in a thread
            def _stream_generate():
                return self.client.chat_stream(**params)
            
            stream = await asyncio.to_thread(_stream_generate)
            
            # Process chunks in a thread to avoid blocking
            def _process_stream():
                chunks = []
                try:
                    for event in stream:
                        if event.type == "content-delta":
                            if hasattr(event, 'delta') and hasattr(event.delta, 'message'):
                                if hasattr(event.delta.message, 'content'):
                                    if hasattr(event.delta.message.content, 'text'):
                                        chunks.append(event.delta.message.content.text)
                        elif event.type == "stream-start":
                            continue
                        elif event.type == "stream-end":
                            break
                except Exception as e:
                    chunks.append(f"Error: {str(e)}")
                return chunks
            
            chunks = await asyncio.to_thread(_process_stream)
            
            # Yield all chunks
            for chunk in chunks:
                yield chunk
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Cohere: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Cohere client."""
        # Cohere client doesn't require explicit cleanup
        self.client = None
        self.logger.info("Cohere provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Cohere configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Cohere API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Cohere model is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            def _test_chat():
                return self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5,
                    temperature=0
                )
            
            response = await asyncio.to_thread(_test_chat)
            
            if self.verbose:
                self.logger.info("Cohere configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("cohere package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Cohere configuration validation failed: {str(e)}")
            return False