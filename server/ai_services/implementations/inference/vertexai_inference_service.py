"""
Vertex AI inference service implementation using unified architecture.

This is a migrated version of the Vertex AI inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/vertex_ai_provider.py (old implementation)
"""

from typing import Any
from collections.abc import AsyncGenerator

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService


class VertexAIInferenceService(UsageReportingMixin, InferenceService, GoogleBaseService):
    """
    Vertex AI inference service using unified architecture.

    Old implementation: ~292 lines (vertex_ai_provider.py)
    New implementation: ~80 lines
    Reduction: ~73%

    Vertex AI provides Google's AI models on Google Cloud Platform with:
    - Enterprise security and compliance
    - Private endpoints
    - Custom model training
    - Model versioning and deployment
    """

    @staticmethod
    def _billed_completion_tokens(usage) -> int:
        """
        Completion-side token count actually billed. candidates_token_count
        alone excludes thoughts_token_count (reasoning/thinking tokens on
        models with thinking enabled), which are billed as output.
        """
        candidates = getattr(usage, "candidates_token_count", None) or 0
        thoughts = getattr(usage, "thoughts_token_count", None) or 0
        return candidates + thoughts

    def __init__(self, config: dict[str, Any]):
        """Initialize the Vertex AI inference service."""
        # Initialize via GoogleBaseService first, which will call ProviderAIService
        # This ensures the model is properly extracted from config
        GoogleBaseService.__init__(self, config, ServiceType.INFERENCE, "vertexai")

        # Get inference-specific configuration (these will override the defaults from InferenceService)
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = self._get_top_k(default=40)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Vertex AI."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            from vertexai.preview.generative_models import GenerativeModel

            # Initialize model
            model = GenerativeModel(self.model)

            # Generate response
            response = await model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_output_tokens": kwargs.get('max_tokens', self.max_tokens),
                    "top_p": kwargs.get('top_p', self.top_p),
                    "top_k": kwargs.get('top_k', self.top_k),
                }
            )

            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_token_count", None),
                    self._billed_completion_tokens(usage),
                    reasoning_tokens=getattr(usage, "thoughts_token_count", None),
                )

            return response.text

        except Exception as e:
            self._handle_google_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Vertex AI."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            from vertexai.preview.generative_models import GenerativeModel

            model = GenerativeModel(self.model)

            response = await model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_output_tokens": kwargs.get('max_tokens', self.max_tokens),
                    "top_p": kwargs.get('top_p', self.top_p),
                    "top_k": kwargs.get('top_k', self.top_k),
                },
                stream=True
            )

            last_usage = None
            async for chunk in response:
                if getattr(chunk, "usage_metadata", None) is not None:
                    last_usage = chunk.usage_metadata
                if chunk.text:
                    yield chunk.text

            if last_usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(last_usage, "prompt_token_count", None),
                    self._billed_completion_tokens(last_usage),
                    reasoning_tokens=getattr(last_usage, "thoughts_token_count", None),
                )

        except Exception as e:
            self._handle_google_error(e, "streaming generation")
            yield f"Error: {str(e)}"
