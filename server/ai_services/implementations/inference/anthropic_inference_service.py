"""
Anthropic inference service implementation using unified architecture.

This is a migrated version of the Anthropic inference provider that uses
the new unified AI services architecture.
"""

import json
from typing import Dict, Any, AsyncGenerator, List

from ...base import ServiceType
from ...providers import AnthropicBaseService
from ...services import InferenceService, ToolCallingResult


class AnthropicInferenceService(InferenceService, AnthropicBaseService):
    """
    Anthropic inference service using unified architecture.

    This implementation leverages:
    1. API key management from AnthropicBaseService
    2. AsyncAnthropic client initialization from AnthropicBaseService
    3. Configuration parsing from base classes
    4. Error handling via _handle_anthropic_error()

    Dramatically simplified with automatic handling of setup and configuration.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic inference service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        AnthropicBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "anthropic")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.1)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    @staticmethod
    def _extract_system_message(messages):
        """
        Extract system messages from the messages list and return them separately.

        The Anthropic Messages API requires system content as a top-level `system`
        parameter, not as a message with role "system".

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Tuple of (system_content_string_or_None, filtered_messages_list)
        """
        system_parts = []
        filtered = []
        for msg in messages:
            if msg.get('role') == 'system':
                system_parts.append(msg.get('content', ''))
            else:
                filtered.append(msg)
        system_content = "\n\n".join(system_parts) if system_parts else None
        return system_content, filtered

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the Anthropic Messages API."""
        if not self.initialized:
            await self.initialize()

        # Convert OpenAI-format tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            fn = tool.get("function", {})
            anthropic_tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })

        # Convert messages (handles tool_calls and tool result turns)
        system_content, anthropic_messages = self._convert_messages_for_tools(messages)

        params: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
        }
        if system_content:
            params["system"] = system_content
        temp = kwargs.pop("temperature", self.temperature)
        if temp is not None:
            params["temperature"] = temp

        try:
            response = await self.client.messages.create(**params)
        except Exception as e:
            self._handle_anthropic_error(e, "tool-calling generation")
            raise

        text = None
        tool_calls_result = None
        tool_use_blocks = []

        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if tool_use_blocks:
            tool_calls_result = [
                {"id": b.id, "name": b.name, "arguments": b.input}
                for b in tool_use_blocks
            ]

        # Normalize to OpenAI-format assistant message for the loop
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls_result:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in tool_calls_result
            ]

        return ToolCallingResult(
            text=text,
            tool_calls=tool_calls_result,
            assistant_message=assistant_msg,
            finish_reason=response.stop_reason or "stop",
        )

    def _convert_messages_for_tools(
        self, messages: List[Dict[str, Any]]
    ):
        """
        Convert an OpenAI-format message list (including tool-call history) to
        Anthropic format, returning (system_content_or_None, anthropic_messages).
        """
        system_content, filtered = self._extract_system_message(messages)
        anthropic_messages = []
        i = 0
        while i < len(filtered):
            msg = filtered[i]
            role = msg.get("role")

            if role == "assistant":
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"].get("arguments") or "{}"),
                    })
                anthropic_messages.append({"role": "assistant", "content": content})

            elif role == "tool":
                # Collect consecutive tool-result messages into one user turn
                tool_results = []
                while i < len(filtered) and filtered[i].get("role") == "tool":
                    t = filtered[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": t.get("tool_call_id", ""),
                        "content": t.get("content", ""),
                    })
                    i += 1
                anthropic_messages.append({"role": "user", "content": tool_results})
                continue  # skip i += 1 below

            else:
                anthropic_messages.append({"role": role, "content": msg.get("content", "")})

            i += 1

        return system_content, anthropic_messages

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Anthropic.

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

            # Anthropic requires system content as a top-level parameter
            system_content, messages = self._extract_system_message(messages)

            # Build parameters using configured values
            # Note: Anthropic API doesn't allow both temperature and top_p
            # Prefer temperature if both are provided
            temperature = kwargs.pop('temperature', self.temperature)
            top_p = kwargs.pop('top_p', self.top_p)

            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                **kwargs  # Any other parameters
            }

            if system_content:
                params["system"] = system_content

            # Only include temperature or top_p, not both
            if temperature is not None:
                params["temperature"] = temperature
            elif top_p is not None:
                params["top_p"] = top_p

            response = await self.client.messages.create(**params)

            return response.content[0].text

        except Exception as e:
            self._handle_anthropic_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Anthropic.

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

            # Anthropic requires system content as a top-level parameter
            system_content, messages = self._extract_system_message(messages)

            # Build parameters using configured values
            # Note: Anthropic API doesn't allow both temperature and top_p
            # Prefer temperature if both are provided
            temperature = kwargs.pop('temperature', self.temperature)
            top_p = kwargs.pop('top_p', self.top_p)

            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                **kwargs  # Any other parameters
            }

            if system_content:
                params["system"] = system_content

            # Only include temperature or top_p, not both
            if temperature is not None:
                params["temperature"] = temperature
            elif top_p is not None:
                params["top_p"] = top_p

            async with self.client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            self._handle_anthropic_error(e, "streaming generation")
            yield f"Error: {str(e)}"
