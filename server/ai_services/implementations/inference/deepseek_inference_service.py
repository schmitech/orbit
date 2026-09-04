"""
DeepSeek inference service implementation using unified architecture.

This is a migrated version of the DeepSeek inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/deepseek_provider.py (old implementation)
"""

from typing import Any
from collections.abc import AsyncGenerator

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService


class DeepSeekInferenceService(UsageReportingMixin, InferenceService, OpenAICompatibleBaseService):
    """
    DeepSeek inference service using unified architecture.

    DeepSeek provides an OpenAI-compatible API at https://api.deepseek.com/v1

    Old implementation: ~215 lines (deepseek_provider.py)
    New implementation: ~100 lines
    Reduction: ~54%
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize the DeepSeek inference service."""
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "deepseek")
        InferenceService.__init__(self, config, "deepseek")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using DeepSeek."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

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
                params["reasoning_effort"] = reasoning_effort

            response = await self.client.chat.completions.create(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                    reasoning_tokens=self._extract_reasoning_tokens(usage),
                    cached_prompt_tokens=getattr(usage, "prompt_cache_hit_tokens", None),
                )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using DeepSeek."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

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
                params["reasoning_effort"] = reasoning_effort

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
                        cached_prompt_tokens=getattr(chunk.usage, "prompt_cache_hit_tokens", None),
                    )

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"
