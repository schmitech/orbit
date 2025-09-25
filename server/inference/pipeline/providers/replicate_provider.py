"""
Replicate Provider for Pipeline Architecture

This module provides a clean Replicate implementation for the pipeline architecture.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class ReplicateProvider(LLMProvider):
    """
    Clean Replicate implementation for the pipeline architecture. 
    
    This provider communicates directly with Replicate's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Replicate provider.
        
        Args:
            config: Configuration dictionary containing Replicate settings
        """
        self.config = config
        replicate_config = config.get("inference", {}).get("replicate", {})
        
        self.api_key = replicate_config.get("api_key")
        self.model = replicate_config.get("model")
        self.temperature = replicate_config.get("temperature", 0.1)
        self.top_p = replicate_config.get("top_p", 0.8)
        self.max_tokens = replicate_config.get("max_tokens", 1024)
        self.stream = replicate_config.get("stream", True)
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Replicate client."""
        try:
            import replicate
            
            if not self.api_key:
                raise ValueError("Replicate API key is required")
            
            self.client = replicate.Client(api_token=self.api_key)
            self.logger.info(f"Initialized Replicate provider with model: {self.model}")
            
        except ImportError:
            self.logger.error("replicate package not installed. Please install with: pip install replicate")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Replicate client: {str(e)}")
            raise

    def _build_input(self, prompt: str, messages: list = None, **kwargs) -> dict:
        """
        Build the input dictionary for the Replicate API.
        """
        # Default input structure
        input_data = {
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", self.top_p),
            "max_new_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        # Handle messages format if provided
        if messages:
            # Extract system and user messages
            system_prompt = ""
            user_prompt = ""
            
            for message in messages:
                if message.get("role") == "system":
                    system_prompt = message.get("content", "")
                elif message.get("role") == "user":
                    user_prompt = message.get("content", "")
            
            if system_prompt:
                input_data["system_prompt"] = system_prompt
            if user_prompt:
                input_data["prompt"] = user_prompt
        else:
            # Handle legacy system prompt format
            if "\nUser:" in prompt and "Assistant:" in prompt:
                parts = prompt.split("\nUser:", 1)
                if len(parts) == 2:
                    system_part = parts[0].strip()
                    user_part = parts[1].replace("Assistant:", "").strip()
                    input_data["system_prompt"] = system_part
                    input_data["prompt"] = user_part

        return input_data

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Replicate.
        
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
            
            input_data = self._build_input(prompt, messages, **kwargs)
            
            if self.verbose:
                self.logger.debug(f"Sending request to Replicate: model={self.model}")

            def _run():
                return self.client.run(self.model, input=input_data)

            output = await asyncio.to_thread(_run)
            return "".join(output)
            
        except Exception as e:
            self.logger.error(f"Error generating response with Replicate: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Replicate.
        
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
            
            input_data = self._build_input(prompt, messages, **kwargs)

            if self.verbose:
                self.logger.debug(f"Starting streaming request to Replicate: model={self.model}")

            def _stream():
                return self.client.stream(self.model, input=input_data)

            stream = await asyncio.to_thread(_stream)
            
            for chunk in stream:
                yield str(chunk)
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Replicate: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Replicate client."""
        self.client = None
        self.logger.info("Replicate provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Replicate configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Replicate API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Replicate model is missing")
                return False
            
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            def _run_validation():
                input_data = {
                    "prompt": "test",
                    "max_new_tokens": 5
                }
                # Use a known fast model for validation if possible
                validation_model = self.model
                return self.client.run(validation_model, input=input_data)

            await asyncio.to_thread(_run_validation)
            
            if self.verbose:
                self.logger.info("Replicate configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("replicate package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Replicate configuration validation failed: {str(e)}")
            return False
