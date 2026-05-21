"""
NEAR AI Cloud inference service implementation.

NEAR AI Cloud provides TEE-backed private inference via an OpenAI-compatible
API at https://cloud-api.near.ai/v1.
"""

from typing import Dict, Any, AsyncGenerator, List

from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService


class NearAIInferenceService(InferenceService, OpenAICompatibleBaseService):
    """NEAR AI Cloud inference service using unified architecture."""

    UNSUPPORTED_PARAMS = {"store", "reasoning_effort", "strict"}

    def __init__(self, config: Dict[str, Any]):
        InferenceService.__init__(self, config, "nearai")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    def _prepare_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        prepared = dict(kwargs)

        if "max_completion_tokens" in prepared and "max_tokens" not in prepared:
            prepared["max_tokens"] = prepared.pop("max_completion_tokens")
        else:
            prepared.pop("max_completion_tokens", None)

        for param in self.UNSUPPORTED_PARAMS:
            prepared.pop(param, None)

        return prepared

    def _normalize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {**message, "role": "system"} if message.get("role") == "developer" else message
            for message in messages
        ]

    def _messages_from_prompt(self, prompt: str) -> List[Dict[str, Any]]:
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                return [
                    {"role": "system", "content": system_part},
                    {"role": "user", "content": user_part},
                ]

        return [{"role": "user", "content": prompt}]

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()

        try:
            kwargs = self._prepare_kwargs(kwargs)
            messages = kwargs.pop("messages", None)
            if messages is None:
                messages = self._messages_from_prompt(prompt)
            messages = self._normalize_messages(messages)

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop("temperature", self.temperature),
                "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
                "top_p": kwargs.pop("top_p", self.top_p),
                **kwargs,
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
            kwargs = self._prepare_kwargs(kwargs)
            messages = kwargs.pop("messages", None)
            if messages is None:
                messages = self._messages_from_prompt(prompt)
            messages = self._normalize_messages(messages)

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop("temperature", self.temperature),
                "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
                "top_p": kwargs.pop("top_p", self.top_p),
                "stream": True,
                **kwargs,
            }

            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"
