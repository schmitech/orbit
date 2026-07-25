"""
OpenAI inference service implementation using unified architecture.

This is a migrated version of the OpenAI inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/openai_provider.py (old implementation)
"""

import json
from typing import Dict, Any, AsyncGenerator, List

import logging

from ...base import ServiceType
from ...providers import OpenAIBaseService
from ...services import InferenceService, ToolCallingResult

logger = logging.getLogger(__name__)


class OpenAIInferenceService(InferenceService, OpenAIBaseService):
    """
    OpenAI inference service using unified architecture.

    This implementation is dramatically simpler because:
    1. API key management handled by OpenAIBaseService
    2. AsyncOpenAI client initialization handled by OpenAIBaseService
    3. Configuration parsing handled by base classes
    4. Connection verification handled by base classes
    5. Error handling via _handle_openai_error()

    Old implementation: ~158 lines
    New implementation: ~70 lines focused only on inference logic
    Reduction: ~56%
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI inference service.

        Args:
            config: Configuration dictionary

        Note: All setup (API key, client, etc.) handled by base classes!
        """
        # Initialize via OpenAIBaseService first, which will call ProviderAIService
        # This ensures the model is properly extracted from config
        OpenAIBaseService.__init__(self, config, ServiceType.INFERENCE, "openai")

        # Get inference-specific configuration (these will override the defaults from InferenceService)
        self.temperature = self._get_temperature(default=0.1)
        self.max_tokens = self._get_max_tokens(default=2000)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using OpenAI.

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
            web_search = kwargs.pop('web_search', False)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Web search uses the Responses API + web_search tool (not chat.completions)
            if web_search:
                params = self._build_web_search_params(messages, **kwargs)
                response = await self.client.responses.create(**params)
                return response.output_text

            # Build parameters using configured values
            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                token_param: token_value,
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None and self._supports_temperature():
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if self._supports_top_p():
                params["top_p"] = top_p_value

            params.update(kwargs)  # Any other parameters

            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using OpenAI.

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
            web_search = kwargs.pop('web_search', False)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Web search uses the Responses API + web_search tool (not chat.completions)
            if web_search:
                params = self._build_web_search_params(messages, stream=True, **kwargs)
                response_stream = await self.client.responses.create(**params)
                async for event in response_stream:
                    if getattr(event, "type", None) == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            yield delta
                return

            # Build parameters using configured values
            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                token_param: token_value,
                "stream": True,
                "stream_options": {"include_usage": True}  # Required for proper streaming in newer SDK versions
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None and self._supports_temperature():
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if self._supports_top_p():
                params["top_p"] = top_p_value

            params.update(kwargs)  # Any other parameters

            logger.debug(f"Creating OpenAI stream with params: model={params['model']}, stream={params['stream']}")

            stream = await self.client.chat.completions.create(**params)

            logger.debug("Stream object created, starting iteration...")

            chunk_count = 0
            debug_enabled = self.logger.isEnabledFor(logging.DEBUG)
            async for chunk in stream:
                chunk_count += 1
                if chunk_count == 1 and debug_enabled:
                    logger.debug("First chunk received from OpenAI")

                if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    if debug_enabled and chunk_count <= 3:
                        logger.debug("Yielding chunk #%s: %r", chunk_count, content[:50])
                    yield content

            logger.debug(f"Streaming complete. Total chunks: {chunk_count}")

        except Exception as e:
            self._handle_openai_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the Responses API."""
        if not self.initialized:
            await self.initialize()

        kw = kwargs.copy()
        token_value = self._resolve_token_value("max_output_tokens", kw)

        params: Dict[str, Any] = {
            "model": self.model,
            "input": self._messages_to_responses_input(messages),
            "max_output_tokens": token_value,
        }
        # Omit tools entirely when none are offered — the OpenAI API rejects an
        # empty tools array, and the final synthesis call passes [] on purpose
        # to force a text answer instead of further tool calls.
        if tools:
            params["tools"] = self._tools_to_responses_format(tools)
            params["tool_choice"] = "auto"
        temp = kw.pop("temperature", self.temperature)
        if temp is not None and self._supports_temperature():
            params["temperature"] = temp
        if self._supports_top_p():
            params["top_p"] = kw.pop("top_p", self.top_p)

        # Chat Completions calls this ``reasoning_effort``; Responses nests it
        # under ``reasoning`` and supports reasoning together with functions.
        reasoning_effort = kw.pop("reasoning_effort", None)
        if reasoning_effort is None:
            reasoning_effort = self._extract_provider_config().get("reasoning_effort")
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}

        try:
            response = await self.client.responses.create(**params)
        except Exception as e:
            self._handle_openai_error(e, "tool-calling generation")
            raise

        output_items = self._response_output_to_dicts(response)
        function_calls = [item for item in output_items if item.get("type") == "function_call"]
        text = getattr(response, "output_text", None)

        # Keep the MCP loop's OpenAI-compatible history contract, while
        # retaining the typed Responses output items.  The latter includes
        # reasoning items and is fed back on the next turn with the function
        # outputs, which preserves the model's reasoning context.
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": text,
            "_openai_responses_output": output_items,
        }
        tool_calls_result = None

        if function_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["call_id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in function_calls
            ]
            tool_calls_result = [
                {
                    "id": tc["call_id"],
                    "name": tc["name"],
                    "arguments": json.loads(tc.get("arguments") or "{}"),
                }
                for tc in function_calls
            ]

        return ToolCallingResult(
            text=text,
            tool_calls=tool_calls_result,
            assistant_message=assistant_msg,
            finish_reason="tool_calls" if function_calls else "stop",
        )

    @staticmethod
    def _tools_to_responses_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Chat Completions function schemas to Responses tool schemas."""
        converted = []
        for tool in tools:
            if tool.get("type") != "function" or "function" not in tool:
                converted.append(tool)
                continue
            function = tool["function"]
            response_tool = {"type": "function", **function}
            # Chat Completions defaults functions to non-strict, whereas
            # Responses prefers strict mode when it can. Preserve the existing
            # MCP schema behavior unless the caller opted into strict mode.
            response_tool.setdefault("strict", False)
            converted.append(response_tool)
        return converted

    @classmethod
    def _messages_to_responses_input(cls, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert the MCP loop's Chat Completions history to Responses items."""
        input_items = []
        for message in messages:
            if message.get("role") == "assistant" and message.get("_openai_responses_output"):
                input_items.extend(message["_openai_responses_output"])
            elif message.get("role") == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": message.get("content", ""),
                })
            elif message.get("role") == "assistant" and message.get("tool_calls"):
                # Support histories produced before this provider migrated.
                input_items.extend({
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": call["function"]["name"],
                    "arguments": call["function"].get("arguments", "{}"),
                } for call in message["tool_calls"])
            else:
                input_items.append({
                    key: value for key, value in message.items()
                    if not key.startswith("_")
                })
        return input_items

    @staticmethod
    def _response_output_to_dicts(response: Any) -> List[Dict[str, Any]]:
        """Return SDK response output items as plain dictionaries for replay."""
        output_items = []
        for item in getattr(response, "output", []) or []:
            if isinstance(item, dict):
                output_items.append(item)
            elif hasattr(item, "model_dump"):
                output_items.append(item.model_dump(exclude_none=True))
            else:
                output_items.append(dict(vars(item)))
        return output_items

    def _build_web_search_params(self, messages: list, stream: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Build parameters for a web-search request via the Responses API.

        The Chat Completions API does not accept a web search tool, so web search
        routes through client.responses.create with the built-in web_search tool.
        The system message is passed as `instructions`; the rest become `input` items.
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
            "max_output_tokens": self._resolve_token_value("max_output_tokens", kwargs),
        }

        if instructions_parts:
            params["instructions"] = "\n\n".join(instructions_parts)

        temperature = kwargs.pop("temperature", self.temperature)
        if temperature is not None and self._supports_temperature():
            params["temperature"] = temperature

        if stream:
            params["stream"] = True

        return params

    def _get_token_parameter_name(self) -> str:
        """Return the correct token-count parameter name for the active model."""
        provider_config = self._extract_provider_config()

        # Allow explicit configuration override
        configured_name = provider_config.get("token_parameter_name") or provider_config.get("token_parameter")
        if isinstance(configured_name, str):
            configured_name = configured_name.strip()
            if configured_name:
                return configured_name

        model_name = (self.model or "").lower()

        # Newer OpenAI chat models expect max_completion_tokens when using the chat.completions API
        modern_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        if model_name.startswith(modern_prefixes):
            return "max_completion_tokens"

        # Default to the legacy chat.completions parameter name
        return "max_tokens"

    def _resolve_token_value(self, token_param: str, kwargs: Dict[str, Any]) -> int:
        """Determine the token limit value while respecting caller overrides."""
        # Pop all known token parameter variants so they don't leak into kwargs
        overrides = {
            "max_tokens": kwargs.pop("max_tokens", None),
            "max_completion_tokens": kwargs.pop("max_completion_tokens", None),
            "max_output_tokens": kwargs.pop("max_output_tokens", None),
        }

        # Caller provided the exact parameter we plan to use
        param_override = overrides.get(token_param)
        if param_override is not None:
            return param_override

        # Fall back to whichever override was provided, regardless of naming
        for value in overrides.values():
            if value is not None:
                return value

        # No override found; use configured default
        return self.max_tokens

    def _supports_temperature(self) -> bool:
        """Return whether the current model supports custom temperature values."""
        model_name = (self.model or "").lower()

        # Newer OpenAI models (gpt-5, o-series) only support default temperature (1.0)
        # and will error if you pass temperature=0.0 or any other value
        unsupported_prefixes = (
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        return not model_name.startswith(unsupported_prefixes)

    def _supports_top_p(self) -> bool:
        """Return whether the current model supports the top_p parameter."""
        model_name = (self.model or "").lower()

        # Current OpenAI docs list top_p as unsupported for newer models (4.1/4o/5/o-series)
        unsupported_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        return not model_name.startswith(unsupported_prefixes)
