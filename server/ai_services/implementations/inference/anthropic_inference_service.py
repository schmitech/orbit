"""
Anthropic inference service implementation using unified architecture.

This is a migrated version of the Anthropic inference provider that uses
the new unified AI services architecture.
"""

import json
from typing import Dict, Any, AsyncGenerator, List
from urllib.parse import urlparse

from ...base import ServiceType
from ...providers import AnthropicBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService, ToolCallingResult


class AnthropicInferenceService(UsageReportingMixin, InferenceService, AnthropicBaseService):
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
        self.max_tokens = self._get_max_tokens(default=1024)

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

    @staticmethod
    def _extract_text_and_citations(content_blocks):
        """
        Concatenate text blocks from a Messages API response and collect any
        web_search_result_location citations attached to them.

        The web_search tool runs server-side; Claude interleaves
        server_tool_use / web_search_tool_result blocks with the text blocks
        that cite them, so the final text is every text block joined in order.
        """
        text_parts = []
        citations = []
        for block in content_blocks:
            if getattr(block, "type", None) != "text":
                continue
            text_parts.append(block.text)
            citations.extend(getattr(block, "citations", None) or [])
        return "".join(text_parts), citations

    @staticmethod
    def _format_citations(citations: List[Any]) -> str:
        """Format web_search_result_location citations as a markdown source list."""
        seen_urls = set()
        lines = []
        for citation in citations:
            if getattr(citation, "type", None) != "web_search_result_location":
                continue
            url = getattr(citation, "url", None)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = getattr(citation, "title", None) or urlparse(url).hostname or url
            lines.append(f"- [{title}]({url})")

        if not lines:
            return ""

        return "\n\n**Sources:**\n" + "\n".join(lines)

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the Anthropic Messages API."""
        usage_sink = self._take_usage_sink(kwargs)
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
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
        }
        # Omit tools when none are offered — the final synthesis call passes []
        # on purpose to force a text answer instead of further tool calls.
        if anthropic_tools:
            params["tools"] = anthropic_tools
        if system_content:
            params["system"] = system_content
        kwargs.pop("temperature", None)
        effort = self._resolve_effort(kwargs)
        if self._supports_effort():
            params["output_config"] = {"effort": effort}

        try:
            # Claude's extended-running requests must use the streaming API.
            # This loop still needs a complete message (including all tool_use
            # blocks), so consume the stream internally and normalize its final
            # message rather than exposing token chunks to the MCP tool loop.
            async with self.client.messages.stream(**params) as stream:
                response = await stream.get_final_message()
        except Exception as e:
            self._handle_anthropic_error(e, "tool-calling generation")
            raise

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._report_usage(
                usage_sink,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
            )

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
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Anthropic requires system content as a top-level parameter
            system_content, messages = self._extract_system_message(messages)

            # Build parameters using configured values
            # Note: Anthropic no longer accepts temperature/top_p for current Claude models
            kwargs.pop('temperature', None)
            kwargs.pop('top_p', None)
            effort = self._resolve_effort(kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                **kwargs  # Any other parameters
            }

            if system_content:
                params["system"] = system_content
            if self._supports_effort():
                params["output_config"] = {"effort": effort}
            if web_search:
                params["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

            response = await self.client.messages.create(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "input_tokens", None),
                    getattr(usage, "output_tokens", None),
                )

            text, citations = self._extract_text_and_citations(response.content)
            if web_search:
                text += self._format_citations(citations)
            return text

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
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Anthropic requires system content as a top-level parameter
            system_content, messages = self._extract_system_message(messages)

            # Build parameters using configured values
            # Note: Anthropic no longer accepts temperature/top_p for current Claude models
            kwargs.pop('temperature', None)
            kwargs.pop('top_p', None)
            effort = self._resolve_effort(kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                **kwargs  # Any other parameters
            }

            if system_content:
                params["system"] = system_content
            if self._supports_effort():
                params["output_config"] = {"effort": effort}
            if web_search:
                params["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

            async with self.client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield text

                # get_final_message() is available once the stream is exhausted
                # and carries the message-level usage totals (input/output
                # tokens are cumulative on Anthropic's message_delta events —
                # this is the final, already-summed value, not something to add to).
                if usage_sink is not None or web_search:
                    final_message = await stream.get_final_message()
                    if usage_sink is not None:
                        usage = getattr(final_message, "usage", None)
                        if usage is not None:
                            self._report_usage(
                                usage_sink,
                                getattr(usage, "input_tokens", None),
                                getattr(usage, "output_tokens", None),
                            )
                    if web_search:
                        _, citations = self._extract_text_and_citations(final_message.content)
                        sources = self._format_citations(citations)
                        if sources:
                            yield sources

        except Exception as e:
            self._handle_anthropic_error(e, "streaming generation")
            yield f"Error: {str(e)}"
