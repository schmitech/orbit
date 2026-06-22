"""
Sakana AI (Fugu) inference service implementation.

Fugu exposes an OpenAI-compatible API at /v1/chat/completions and a
Responses API at /v1/responses.  The base URL is configured via FUGU_BASE_URL.
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, List

from openai import RateLimitError

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...services import InferenceService, ToolCallingResult

logger = logging.getLogger(__name__)


class FuguInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    Sakana AI (Fugu) inference service.

    Uses the OpenAI-compatible base for client setup; adds support for
    Fugu-specific reasoning_effort and the Responses API.
    """

    def __init__(self, config: Dict[str, Any]):
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "fugu")
        InferenceService.__init__(self, config, "fugu")

        provider_config = self._extract_provider_config()
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=4096)
        self.top_p = self._get_top_p(default=1.0)
        self.reasoning_effort = provider_config.get("reasoning_effort", "high")

    async def verify_connection(self) -> bool:
        """Verify connection by listing models only — skip the test-chat fallback.

        The base class falls back to a real chat.completions call when models.list()
        fails, which consumes quota and generates misleading retry logs. Fugu returns
        429 on both when balance is exhausted, so we treat any models.list() failure
        as a non-fatal verification miss rather than burning a request.
        """
        try:
            await self.client.models.list()
            logger.debug("Fugu connection verified via models list")
            return True
        except RateLimitError:
            logger.warning("Fugu credit balance exhausted — skipping test request during verification")
            return False
        except Exception as e:
            logger.debug("Fugu models list unavailable (%s) — skipping verification", str(e))
            return False

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation via the Fugu chat completions API."""
        if not self.initialized:
            await self.initialize()

        params: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop("temperature", self.temperature),
            "max_completion_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "top_p": kwargs.pop("top_p", self.top_p),
            **kwargs,
        }
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
        """Generate a response using the Fugu chat completions API."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop("messages", None)
            web_search = kwargs.pop("web_search", False)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            if web_search:
                params = self._build_responses_api_params(messages, **kwargs)
                response = await self.client.responses.create(**params)
                return response.output_text

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop("temperature", self.temperature),
                "max_completion_tokens": kwargs.pop("max_tokens", self.max_tokens),
                "top_p": kwargs.pop("top_p", self.top_p),
                **kwargs,
            }
            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream a response using the Fugu chat completions API."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop("messages", None)
            web_search = kwargs.pop("web_search", False)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            if web_search:
                params = self._build_responses_api_params(messages, stream=True, **kwargs)
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
                "temperature": kwargs.pop("temperature", self.temperature),
                "max_completion_tokens": kwargs.pop("max_tokens", self.max_tokens),
                "top_p": kwargs.pop("top_p", self.top_p),
                "stream": True,
                **kwargs,
            }
            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except RateLimitError as e:
            # Credit exhaustion returns 429 — yield a friendly message rather than
            # propagating so the client receives a readable stream response.
            msg = "Sakana AI credit balance is exhausted. Please top up your account."
            logger.warning("Fugu rate limit / credit exhausted: %s", str(e))
            yield msg
        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _build_responses_api_params(
        self, messages: list, stream: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """Build parameters for the Fugu Responses API (/v1/responses)."""
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
            "reasoning": {"effort": self.reasoning_effort},
        }

        if instructions_parts:
            params["instructions"] = "\n\n".join(instructions_parts)

        temperature = kwargs.pop("temperature", self.temperature)
        if temperature is not None:
            params["temperature"] = temperature

        if stream:
            params["stream"] = True

        return params
