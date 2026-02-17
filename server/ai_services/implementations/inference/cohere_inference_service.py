"""
Cohere inference service implementation using OpenAI-compatible API.

Uses Cohere's OpenAI compatibility endpoint (https://api.cohere.ai/compatibility/v1)
via the OpenAI SDK, matching the same pattern as Groq, Mistral, and other
OpenAI-compatible providers.

This avoids Cohere SDK-specific quirks with message formatting, streaming,
and response handling by using the standard OpenAI chat completions interface.
"""

from typing import Dict, Any, AsyncGenerator

from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService


class CohereInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    Cohere inference service using OpenAI-compatible API.

    Uses the standard OpenAI SDK pointed at Cohere's compatibility endpoint,
    identical to how Groq, Mistral, and other providers work.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Cohere inference service."""
        InferenceService.__init__(self, config, "cohere")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.3)
        self.max_tokens = self._get_max_tokens(default=8000)
        self.top_p = self._get_top_p(default=0.9)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Cohere via OpenAI-compatible API."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - extract system prompt if present
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

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                **kwargs
            }

            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Cohere via OpenAI-compatible API."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)

            if messages is None:
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

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                "stream": True,
                **kwargs
            }

            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"
