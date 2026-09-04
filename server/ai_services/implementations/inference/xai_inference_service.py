"""
xAI (Grok) inference service implementation using unified architecture.

This is a migrated version of the xAI inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/xai_provider.py (old implementation)
"""

import json
from typing import Any
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService, ToolCallingResult


class XAIInferenceService(UsageReportingMixin, InferenceService, OpenAICompatibleBaseService):
    """
    xAI (Grok) inference service using unified architecture.

    xAI provides an OpenAI-compatible API at https://api.x.ai/v1
    xAI is Elon Musk's AI company, providing the Grok models.

    Old implementation: ~283 lines (xai_provider.py)
    New implementation: ~100 lines
    Reduction: ~65%
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the xAI inference service."""
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "xai")
        InferenceService.__init__(self, config, "xai")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)

    @staticmethod
    def _extract_cached_prompt_tokens(usage: Any) -> Any:
        """
        Cached-prompt subset of prompt tokens, from whichever
        OpenAI-compatible usage shape xAI reports it under: chat.completions
        nests it under prompt_tokens_details.cached_tokens, the Responses API
        (used for web_search=True, see _build_web_search_params) nests it
        under input_tokens_details.cached_tokens instead — same field,
        different parent, so both are checked here.
        """
        details = getattr(usage, "prompt_tokens_details", None) or getattr(usage, "input_tokens_details", None)
        return getattr(details, "cached_tokens", None) if details is not None else None

    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the xAI (Grok) API."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        reasoning_effort = self._resolve_reasoning_effort(kwargs)

        params: dict[str, Any] = {
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

        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}

        try:
            response = await self.client.chat.completions.create(**params)
        except Exception as e:
            self._handle_openai_compatible_error(e, "tool-calling generation")
            raise

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._report_usage(
                usage_sink,
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
                reasoning_tokens=self._extract_reasoning_tokens(usage),
                cached_prompt_tokens=self._extract_cached_prompt_tokens(usage),
            )

        choice = response.choices[0]
        msg = choice.message

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
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
        usage_sink = self._take_usage_sink(kwargs)
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
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self._report_usage(
                        usage_sink,
                        getattr(usage, "input_tokens", None),
                        getattr(usage, "output_tokens", None),
                        reasoning_tokens=self._extract_reasoning_tokens(usage),
                        cached_prompt_tokens=self._extract_cached_prompt_tokens(usage),
                    )
                return response.output_text + self._format_url_citations(self._extract_annotations(response))

            reasoning_effort = self._resolve_reasoning_effort(kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                **kwargs
            }
            if reasoning_effort:
                params["reasoning"] = {"effort": reasoning_effort}

            response = await self.client.chat.completions.create(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    reasoning_tokens=self._extract_reasoning_tokens(usage),
                    cached_prompt_tokens=self._extract_cached_prompt_tokens(usage),
                )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using xAI (Grok)."""
        usage_sink = self._take_usage_sink(kwargs)
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
                annotations = []
                final_response = None
                async for event in response_stream:
                    event_type = getattr(event, "type", None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            yield delta
                    elif event_type == "response.output_text.annotation.added":
                        annotation = getattr(event, "annotation", None)
                        if annotation:
                            annotations.append(annotation)
                    elif event_type == "response.completed":
                        final_response = getattr(event, "response", None)

                if final_response is not None:
                    usage = getattr(final_response, "usage", None)
                    if usage is not None:
                        self._report_usage(
                            usage_sink,
                            getattr(usage, "input_tokens", None),
                            getattr(usage, "output_tokens", None),
                            reasoning_tokens=self._extract_reasoning_tokens(usage),
                            cached_prompt_tokens=self._extract_cached_prompt_tokens(usage),
                        )

                sources = self._format_url_citations(annotations)
                if sources:
                    yield sources
                return

            reasoning_effort = self._resolve_reasoning_effort(kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                "stream": True,
                "stream_options": {"include_usage": True},
                **kwargs
            }
            if reasoning_effort:
                params["reasoning"] = {"effort": reasoning_effort}

            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                elif getattr(chunk, "usage", None):
                    self._report_usage(
                        usage_sink,
                        getattr(chunk.usage, "prompt_tokens", None),
                        getattr(chunk.usage, "completion_tokens", None),
                        reasoning_tokens=self._extract_reasoning_tokens(chunk.usage),
                        cached_prompt_tokens=self._extract_cached_prompt_tokens(chunk.usage),
                    )

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _build_web_search_params(self, messages: list, stream: bool = False, **kwargs) -> dict[str, Any]:
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

        params: dict[str, Any] = {
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

        reasoning_effort = self._resolve_reasoning_effort(kwargs)
        if reasoning_effort:
            params["reasoning"] = {"effort": reasoning_effort}

        if stream:
            params["stream"] = True

        return params

    @staticmethod
    def _extract_annotations(response: Any) -> list[Any]:
        """Collect url_citation annotations from a non-streaming Responses API result."""
        annotations = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", []) or []:
                annotations.extend(getattr(part, "annotations", []) or [])
        return annotations

    @staticmethod
    def _format_url_citations(annotations: list[Any]) -> str:
        """Format Responses API url_citation annotations as a markdown source list.

        xAI populates ``title`` with the citation index (e.g. "1") rather than
        a real page title, so a bare-digit title is treated as absent and the
        URL's hostname is used as the display text instead.
        """
        seen_urls = set()
        lines = []
        for annotation in annotations:
            if isinstance(annotation, dict):
                url = annotation.get("url")
                title = annotation.get("title")
            else:
                url = getattr(annotation, "url", None)
                title = getattr(annotation, "title", None)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            if not title or title.strip().isdigit():
                title = urlparse(url).hostname or url

            lines.append(f"- [{title}]({url})")

        if not lines:
            return ""

        return "\n\n**Sources:**\n" + "\n".join(lines)

    def _supports_reasoning_effort(self) -> bool:
        """
        Return whether the current model supports the reasoning_effort parameter.

        See https://docs.x.ai/developers/model-capabilities/text/reasoning#the-reasoning_effort-parameter
        """
        model_name = (self.model or "").lower()
        supported_prefixes = (
            "grok-4.5",
            "grok-4.20",
        )
        return model_name.startswith(supported_prefixes)

    def _resolve_reasoning_effort(self, kwargs: dict[str, Any]) -> Any:
        """
        Resolve the reasoning effort level for the current request.

        Accepts either the native ``reasoning_effort`` kwarg or the
        provider-agnostic ``effort`` override (shared with allowed_models
        overrides), falling back to the same keys in inference.yaml. Returns
        None when the current model doesn't support reasoning effort. xAI
        nests this under ``reasoning: {"effort": ...}`` rather than as a
        top-level parameter.
        """
        if not self._supports_reasoning_effort():
            kwargs.pop("reasoning_effort", None)
            kwargs.pop("effort", None)
            return None

        reasoning_effort = kwargs.pop("reasoning_effort", None)
        if reasoning_effort is None:
            reasoning_effort = kwargs.pop("effort", None)
        if reasoning_effort is None:
            provider_config = self._extract_provider_config()
            reasoning_effort = provider_config.get("reasoning_effort") or provider_config.get("effort")
        return reasoning_effort
