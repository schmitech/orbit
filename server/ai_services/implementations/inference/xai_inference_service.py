"""
xAI (Grok) inference service implementation using unified architecture.

This is a migrated version of the xAI inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/xai_provider.py (old implementation)
"""

import json
from typing import Dict, Any, AsyncGenerator, List

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService, ToolCallingResult


class XAIInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    xAI (Grok) inference service using unified architecture.

    xAI provides an OpenAI-compatible API at https://api.x.ai/v1
    xAI is Elon Musk's AI company, providing the Grok models.

    Old implementation: ~283 lines (xai_provider.py)
    New implementation: ~100 lines
    Reduction: ~65%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the xAI inference service."""
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "xai")
        InferenceService.__init__(self, config, "xai")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the xAI (Grok) API."""
        if not self.initialized:
            await self.initialize()

        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self.temperature),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "top_p": kwargs.pop("top_p", self.top_p),
            **kwargs,
        }
        # Omit tools when none are offered — the final synthesis call passes []
        # on purpose to force a text answer instead of further tool calls.
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**params)
        except Exception as e:
            self._handle_openai_compatible_error(e, "tool-calling generation")
            raise

        choice = response.choices[0]
        msg = choice.message

        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": msg.content}
        tool_calls_result = None

        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
            tool_calls_result = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments or "{}"),
                }
                for tc in msg.tool_calls
            ]

        return ToolCallingResult(
            text=msg.content,
            tool_calls=tool_calls_result,
            assistant_message=assistant_msg,
            finish_reason=choice.finish_reason or "stop",
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using xAI (Grok)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            # Web search uses the Responses API + web_search tool (xAI is Responses-API
            # compatible); chat.completions does not accept it.
            if web_search:
                params = self._build_web_search_params(messages, **kwargs)
                response = await self.client.responses.create(**params)
                return response.output_text

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
        """Generate streaming response using xAI (Grok)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            # Web search uses the Responses API + web_search tool (see generate()).
            if web_search:
                params = self._build_web_search_params(messages, stream=True, **kwargs)
                response_stream = await self.client.responses.create(**params)
                async for event in response_stream:
                    if getattr(event, "type", None) == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            yield delta
                return

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

    def _build_web_search_params(self, messages: list, stream: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Build parameters for a web-search request via the Responses API.

        xAI exposes web search through the OpenAI-compatible Responses API
        (tools=[{"type": "web_search"}]); chat.completions does not accept it.
        The system message becomes `instructions`; the rest become `input` items.
        """
        instructions_parts = []
        input_items = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("system", "developer"):
                if content:
                    instructions_parts.append(content)
            else:
                input_items.append({"role": role, "content": content})

        params: Dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "tools": [{"type": "web_search"}],
            "max_output_tokens": kwargs.pop("max_tokens", self.max_tokens),
        }

        if instructions_parts:
            params["instructions"] = "\n\n".join(instructions_parts)

        temperature = kwargs.pop("temperature", self.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        if stream:
            params["stream"] = True

        return params
