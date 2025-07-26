"""
Ollama Provider for Pipeline Architecture

This module provides a clean Ollama implementation for the pipeline architecture.
"""

import json
import logging
import time
from typing import Dict, Any, AsyncGenerator
import aiohttp
from .llm_provider import LLMProvider

class OllamaProvider(LLMProvider):
    """
    Clean Ollama implementation for the pipeline architecture.
    
    This provider communicates directly with Ollama's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama provider.
        
        Args:
            config: Configuration dictionary containing Ollama settings
        """
        self.config = config
        
        # Get Ollama specific configuration
        ollama_config = config.get('inference', {}).get('ollama', {})
        if not ollama_config:
            ollama_config = config.get('ollama', {})  # Backward compatibility
        
        self.base_url = ollama_config.get('base_url', 'http://localhost:11434')
        self.model = ollama_config.get('model', 'gemma3:1b')
        self.temperature = ollama_config.get('temperature', 0.1)
        self.top_p = ollama_config.get('top_p', 0.8)
        self.top_k = ollama_config.get('top_k', 20)
        self.repeat_penalty = ollama_config.get('repeat_penalty', 1.1)
        self.num_predict = ollama_config.get('num_predict', 1024)
        self.num_ctx = ollama_config.get('num_ctx', 8192)
        self.stream = ollama_config.get('stream', True)
        self.verbose = ollama_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self) -> None:
        """Initialize the Ollama provider."""
        # Test connection to verify Ollama is running
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        self.logger.info(f"Initialized Ollama provider with model: {self.model}")
                    else:
                        raise Exception(f"Failed to connect to Ollama: {response.status}")
        except Exception as e:
            self.logger.error(f"Error initializing Ollama provider: {str(e)}")
            raise
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Ollama.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        try:
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "repeat_penalty": self.repeat_penalty,
                        "num_predict": self.num_predict,
                        **kwargs
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        raise Exception(f"Failed to generate response: {error_text}")
                    
                    data = await response.json()
                    response_text = data.get("response", "")
                    
                    processing_time = time.time() - start_time
                    if self.verbose:
                        self.logger.info(f"Ollama generation completed in {processing_time:.3f}s")
                    
                    return response_text
                    
        except Exception as e:
            self.logger.error(f"Error generating response with Ollama: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": True,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "repeat_penalty": self.repeat_penalty,
                        "num_predict": self.num_predict,
                        **kwargs
                    },
                    timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        yield f"Error: Failed to generate response: {error_text}"
                        return
                    
                    # Parse the streaming response
                    buffer = ""
                    async for line in response.content:
                        chunk = line.decode('utf-8').strip()
                        if not chunk:
                            continue
                        
                        try:
                            data = json.loads(chunk)
                            if "response" in data:
                                buffer += data["response"]
                                yield data["response"]
                            
                            if data.get("done", False):
                                break
                                
                        except json.JSONDecodeError:
                            self.logger.error(f"Error parsing JSON: {chunk}")
                            continue
                            
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Ollama: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Ollama provider."""
        # No specific cleanup needed for Ollama
        self.logger.info("Ollama provider cleanup completed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Ollama configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.base_url:
                self.logger.error("Ollama base URL is missing")
                return False
            
            if not self.model:
                self.logger.error("Ollama model is missing")
                return False
            
            # Test connection with a simple request
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as response:
                    if response.status == 200:
                        return True
                    else:
                        self.logger.error(f"Failed to connect to Ollama: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Ollama configuration validation failed: {str(e)}")
            return False 