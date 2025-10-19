"""
Z.AI inference service implementation using unified architecture.

This is a migrated version of the Z.AI inference provider that uses
the new unified AI services architecture.
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import ZaiBaseService
from ..services import InferenceService


class ZaiInferenceService(InferenceService, ZaiBaseService):
    """
    Z.AI inference service using unified architecture.

    This implementation leverages the Z.AI Python SDK for chat completions
    with support for both streaming and non-streaming responses.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Z.AI inference service.

        Args:
            config: Configuration dictionary

        Note: All setup (API key, client, etc.) handled by base classes!
        """
        # Initialize via ZaiBaseService first, which will call ProviderAIService
        # This ensures the model is properly extracted from config
        ZaiBaseService.__init__(self, config, ServiceType.INFERENCE, "zai")

        # Get inference-specific configuration (these will override the defaults from InferenceService)
        self.temperature = self._get_temperature(default=0.1)
        self.max_tokens = self._get_max_tokens(default=2000)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Z.AI.

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
                "max_tokens": self.max_tokens,
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None:
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if top_p_value is not None:
                params["top_p"] = top_p_value

            # Handle other Z.AI specific parameters
            if 'stream' in kwargs:
                params["stream"] = kwargs.pop('stream')

            params.update(kwargs)  # Any other parameters

            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_zai_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Z.AI.

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
                "max_tokens": self.max_tokens,
                "stream": True,
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None:
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if top_p_value is not None:
                params["top_p"] = top_p_value

            params.update(kwargs)  # Any other parameters

            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_zai_error(e, "streaming generation")
            yield f"Error: {str(e)}"
