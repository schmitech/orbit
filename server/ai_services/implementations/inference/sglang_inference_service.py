"""SGLang inference service using its OpenAI-compatible server API.

SGLang is launched and managed externally.  This service communicates with its
``/v1`` endpoint; it deliberately does not import the optional ``sglang``
package or load models in-process.
"""

import json
from typing import Any, AsyncGenerator, Dict, List

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService, ToolCallingResult


class SGLangInferenceService(InferenceService, OpenAICompatibleBaseService):
    """Text inference through a running SGLang OpenAI-compatible server."""

    def __init__(self, config: Dict[str, Any]):
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "sglang")
        InferenceService.__init__(self, config, "sglang")

        provider_config = self._extract_provider_config()
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = provider_config.get("top_k")
        self.repetition_penalty = provider_config.get("repetition_penalty")
        self.presence_penalty = provider_config.get("presence_penalty", 0.0)
        self.frequency_penalty = provider_config.get("frequency_penalty", 0.0)
        self.stop_tokens = provider_config.get("stop", [])

    def _resolve_api_key(self, env_var_name: str, config_key: str = "api_key") -> str:
        """Allow SGLang's default unauthenticated server while supporting --api-key."""
        return super()._resolve_api_key(env_var_name, config_key) or "not-needed"

    def _get_base_url(self, default_url: str) -> str:
        """Use an explicit URL when supplied, otherwise construct one from host/port."""
        provider_config = self._extract_provider_config()
        if base_url := provider_config.get("base_url"):
            return base_url
        host = provider_config.get("host", "localhost")
        port = provider_config.get("port", 30000)
        return f"http://{host}:{port}/v1"

    def _build_messages(self, prompt: str, messages: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return messages if messages is not None else [{"role": "user", "content": prompt}]

    def _build_params(self, messages: List[Dict[str, Any]], kwargs: Dict[str, Any], *, stream: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self.temperature),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "top_p": kwargs.pop("top_p", self.top_p),
            "presence_penalty": kwargs.pop("presence_penalty", self.presence_penalty),
            "frequency_penalty": kwargs.pop("frequency_penalty", self.frequency_penalty),
            **kwargs,
        }
        top_k = params.pop("top_k", self.top_k)
        if top_k is not None and top_k > 0:
            params["top_k"] = top_k
        repetition_penalty = params.pop("repetition_penalty", self.repetition_penalty)
        if repetition_penalty is not None:
            params["repetition_penalty"] = repetition_penalty
        stop = params.pop("stop", self.stop_tokens)
        if stop:
            params["stop"] = stop
        if stream:
            params["stream"] = True
        return params

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()
        try:
            messages = self._build_messages(prompt, kwargs.pop("messages", None))
            response = await self.client.chat.completions.create(
                **self._build_params(messages, kwargs)
            )
            return response.choices[0].message.content
        except Exception as error:
            self._handle_openai_compatible_error(error, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        try:
            messages = self._build_messages(prompt, kwargs.pop("messages", None))
            response = await self.client.chat.completions.create(
                **self._build_params(messages, kwargs, stream=True)
            )
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as error:
            self._handle_openai_compatible_error(error, "streaming generation")
            raise

    async def batch_generate(self, prompts: List[str], **kwargs) -> List[str]:
        """Generate each API request in order, matching vLLM's remote-mode behavior."""
        return [await self.generate(prompt, **kwargs) for prompt in prompts]

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        if not self.initialized:
            await self.initialize()
        try:
            params = self._build_params(messages, kwargs)
            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"
            response = await self.client.chat.completions.create(**params)
        except Exception as error:
            self._handle_openai_compatible_error(error, "tool-calling generation")
            raise

        choice = response.choices[0]
        message = choice.message
        assistant_message: Dict[str, Any] = {"role": "assistant", "content": message.content}
        tool_calls_result = None
        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in message.tool_calls
            ]
            tool_calls_result = [
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": json.loads(call.function.arguments or "{}"),
                }
                for call in message.tool_calls
            ]

        return ToolCallingResult(
            text=message.content,
            tool_calls=tool_calls_result,
            assistant_message=assistant_message,
            finish_reason=choice.finish_reason or "stop",
        )
