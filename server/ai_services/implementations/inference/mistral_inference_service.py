"""
Mistral inference service implementation using unified architecture.

This is a migrated version of the Mistral inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/mistral_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers import OpenAICompatibleBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService


class MistralInferenceService(UsageReportingMixin, InferenceService, OpenAICompatibleBaseService):
    """
    Mistral inference service using unified architecture.

    Mistral provides an OpenAI-compatible API at https://api.mistral.ai/v1
    This allows us to use the AsyncOpenAI client with Mistral's endpoints.

    Old implementation: ~204 lines (mistral_provider.py)
    New implementation: ~100 lines
    Reduction: ~51%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Mistral inference service."""
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "mistral")
        InferenceService.__init__(self, config, "mistral")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Mistral."""
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
                )

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_compatible_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Mistral."""
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
                    )

        except Exception as e:
            self._handle_openai_compatible_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _supports_reasoning_effort(self) -> bool:
        """
        Return whether the current model supports the reasoning_effort parameter.

        See https://docs.mistral.ai/studio-api/conversations/reasoning
        """
        model_name = (self.model or "").lower()
        reasoning_prefixes = (
            "mistral-small",
            "mistral-medium-3-5",
        )
        return model_name.startswith(reasoning_prefixes)

    def _resolve_reasoning_effort(self, kwargs: Dict[str, Any]) -> Any:
        """
        Resolve the reasoning effort level for the current request.

        Accepts either the Mistral-native ``reasoning_effort`` kwarg or the
        provider-agnostic ``effort`` override (shared with allowed_models
        overrides), falling back to the same keys in inference.yaml. Returns
        None when the current model doesn't support reasoning effort.
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
