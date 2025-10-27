"""
Anthropic inference service implementation using unified architecture.

This is a migrated version of the Anthropic inference provider that uses
the new unified AI services architecture.
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import AnthropicBaseService
from ..services import InferenceService


class AnthropicInferenceService(InferenceService, AnthropicBaseService):
    """
    Anthropic inference service using unified architecture.

    This implementation leverages:
    1. API key management from AnthropicBaseService
    2. AsyncAnthropic client initialization from AnthropicBaseService
    3. Configuration parsing from base classes
    4. Error handling via _handle_anthropic_error()

    Dramatically simplified with automatic handling of setup and configuration.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic inference service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        AnthropicBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "anthropic")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.1)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Anthropic.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                **kwargs  # Any other parameters
            }

            response = await self.client.messages.create(**params)

            return response.content[0].text

        except Exception as e:
            self._handle_anthropic_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Anthropic.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                **kwargs  # Any other parameters
            }

            async with self.client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            self._handle_anthropic_error(e, "streaming generation")
            yield f"Error: {str(e)}"
