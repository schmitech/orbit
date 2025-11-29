"""
Groq inference service implementation using unified architecture.

This is a migrated version of the Groq inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/groq_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService


class GroqInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    Groq inference service using unified architecture.

    This implementation is dramatically simpler because:
    1. API key management handled by OpenAICompatibleBaseService
    2. AsyncOpenAI client initialization handled by base class (pointing to Groq's API)
    3. Configuration parsing handled by base classes
    4. Connection verification handled by base classes
    5. Error handling via _handle_openai_compatible_error()

    Old implementation: ~212 lines (groq_provider.py)
    New implementation: ~100 lines focused only on inference logic
    Reduction: ~53%

    Groq provides an OpenAI-compatible API at https://api.groq.com/openai/v1
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Groq inference service.

        Args:
            config: Configuration dictionary

        Note: All setup (API key, client, etc.) handled by base classes!
        """
        # Initialize via InferenceService which will cooperate with OpenAICompatibleBaseService
        InferenceService.__init__(self, config, "groq")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Groq.

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
                # Groq supports system prompts, so try to extract if present
                if "\nUser:" in prompt and "Assistant:" in prompt:
                    parts = prompt.split("\nUser:", 1)
                    if len(parts) == 2:
                        system_part = parts[0].strip()
                        user_part = parts[1].replace("Assistant:", "").strip()
                        messages = [
                            {"role": "system", "content": system_part},
                            {"role": "user", "content": user_part}
                        ]
                else:
                    messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                **kwargs  # Any other Groq-specific parameters
            }

            # Use the OpenAI client (pointing to Groq's API)
            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Groq.

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
                if "\nUser:" in prompt and "Assistant:" in prompt:
                    parts = prompt.split("\nUser:", 1)
                    if len(parts) == 2:
                        system_part = parts[0].strip()
                        user_part = parts[1].replace("Assistant:", "").strip()
                        messages = [
                            {"role": "system", "content": system_part},
                            {"role": "user", "content": user_part}
                        ]
                else:
                    messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                "stream": True,
                **kwargs  # Any other Groq-specific parameters
            }

            # Use the OpenAI client (pointing to Groq's API)
            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"
