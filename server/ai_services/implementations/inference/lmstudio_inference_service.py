"""
LM Studio inference service implementation.

LM Studio runs a local OpenAI-compatible server at http://localhost:1234/v1.
No authentication is required; the api_key config value is a placeholder
that the local server ignores (conventional value: "lm-studio").
"""

from typing import Any
from collections.abc import AsyncGenerator

from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService


class LMStudioInferenceService(InferenceService, OpenAICompatibleBaseService):
    """LM Studio inference service using unified architecture."""

    def __init__(self, config: dict[str, Any]):
        InferenceService.__init__(self, config, "lmstudio")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()

        try:
            messages = self._build_messages(prompt, kwargs)

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

        except Exception as e:  # noqa: BLE001 - provider boundary fallback
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()

        try:
            messages = self._build_messages(prompt, kwargs)

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

        except Exception as e:  # noqa: BLE001 - provider boundary fallback
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {e!s}"
