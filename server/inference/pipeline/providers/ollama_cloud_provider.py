"""
Ollama Cloud Provider for Pipeline Architecture
"""

import logging
from typing import Dict, Any, AsyncGenerator
from ollama import AsyncClient
from .llm_provider import LLMProvider

class OllamaCloudProvider(LLMProvider):
    """
    Ollama Cloud implementation for the pipeline architecture.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama Cloud provider.
        
        Args:
            config: Configuration dictionary containing Ollama Cloud settings
        """
        self.config = config
        self.ollama_cloud_config = config.get('inference', {}).get('ollama_cloud', {})
        if not self.ollama_cloud_config:
            self.ollama_cloud_config = config.get('ollama_cloud', {})

        self.api_key = self.ollama_cloud_config.get("api_key")
        self.model = self.ollama_cloud_config.get("model")

        # Extract options for the Ollama client
        self.options = {
            "temperature": self.ollama_cloud_config.get("temperature", 0.1),
            "top_p": self.ollama_cloud_config.get("top_p", 0.8),
            "top_k": self.ollama_cloud_config.get("top_k"),
            "repeat_penalty": self.ollama_cloud_config.get("repeat_penalty"),
            "num_predict": self.ollama_cloud_config.get("num_predict", 1024),
        }
        # Filter out None values so we don't send them
        self.options = {k: v for k, v in self.options.items() if v is not None}

        self.stream = self.ollama_cloud_config.get("stream", True)
        self.client = None
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self, **kwargs) -> None:
        """Initialize the Ollama Cloud client."""
        if not self.api_key:
            raise ValueError("Ollama Cloud API key is missing.")
        
        self.client = AsyncClient(
            host="https://ollama.com",
            headers={'Authorization': f'{self.api_key}'}
        )
        self.logger.info(f"Initialized OllamaCloudProvider with model: {self.model}")
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Ollama Cloud.
        """
        if not self.client:
            await self.initialize()
        
        try:
            messages = [{"role": "user", "content": prompt}]
            
            response = await self.client.chat(
                model=self.model,
                messages=messages,
                options=self.options,
                **kwargs
            )
            
            return response['message']['content']
            
        except Exception as e:
            self.logger.error(f"Error generating response with Ollama Cloud: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama Cloud.
        """
        if not self.client:
            await self.initialize()
        
        try:
            messages = [{"role": "user", "content": prompt}]
            
            stream = await self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options=self.options,
                **kwargs
            )
            
            async for chunk in stream:
                content = chunk.get('message', {}).get('content')
                if content:
                    yield content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Ollama Cloud: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Ollama Cloud client."""
        if self.client:
            # The ollama client does not have an explicit close method in the async client.
            pass
    
    async def validate_config(self) -> bool:
        """
        Validate the Ollama Cloud configuration.
        """
        try:
            if not self.api_key:
                self.logger.error("Ollama Cloud API key is missing")
                return False
            
            if not self.model:
                self.logger.error("Ollama Cloud model is missing")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ollama Cloud configuration validation failed: {str(e)}")
            return False
