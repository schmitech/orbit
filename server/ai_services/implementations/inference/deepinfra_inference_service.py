"""
DeepInfra inference service implementation.

DeepInfra provides cost-effective hosted inference for open-source models
via an OpenAI-compatible API at https://api.deepinfra.com/v1/openai.
"""

from typing import Dict, Any, AsyncGenerator

from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService


class DeepInfraInferenceService(InferenceService, OpenAICompatibleBaseService):
    """DeepInfra inference service using unified architecture."""

    def __init__(self, config: Dict[str, Any]):
        InferenceService.__init__(self, config, "deepinfra")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
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
                **kwargs
            }

            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
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
