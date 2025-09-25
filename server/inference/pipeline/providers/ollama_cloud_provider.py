"""
Ollama Cloud Provider for Pipeline Architecture
"""

import logging
from typing import Dict, Any, AsyncGenerator
from ollama import AsyncClient
from .ollama_base_provider import OllamaBaseProvider


class OllamaCloudProvider(OllamaBaseProvider):
    """
    Ollama Cloud implementation for the pipeline architecture.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama Cloud provider.

        Args:
            config: Configuration dictionary containing Ollama Cloud settings
        """
        # Initialize base provider
        super().__init__(config, 'ollama_cloud')

        # Cloud-specific settings
        self.api_key = self.provider_config.get("api_key")
        self.client = None

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

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()

        try:
            # Extract messages if provided
            messages = kwargs.pop('messages', None)
            messages = self.prepare_messages(prompt, messages)

            # Get generation options
            options = self.get_generation_options()

            response = await self.client.chat(
                model=self.model,
                messages=messages,
                options=options,
                **kwargs
            )

            return response['message']['content']

        except Exception as e:
            self.logger.error(f"Error generating response with Ollama Cloud: {str(e)}")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama Cloud.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()

        try:
            # Extract messages if provided
            messages = kwargs.pop('messages', None)
            messages = self.prepare_messages(prompt, messages)

            # Get generation options
            options = self.get_generation_options()

            stream = await self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options=options,
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
        self.logger.info("Ollama Cloud provider cleanup completed")

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