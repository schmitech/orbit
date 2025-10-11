"""
Perplexity inference service implementation using unified architecture.

This is a migrated version of the Perplexity inference provider that uses
the new unified AI services architecture with OpenAI-compatible base class.

Compare with: server/inference/pipeline/providers/perplexity_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import OpenAICompatibleBaseService
from ..services import InferenceService


class PerplexityInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    Perplexity inference service using unified architecture.

    Perplexity provides an OpenAI-compatible API at https://api.perplexity.ai

    Old implementation: ~182 lines (perplexity_provider.py)
    New implementation: ~100 lines
    Reduction: ~45%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Perplexity inference service."""
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "perplexity")
        InferenceService.__init__(self, config, "perplexity")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.2)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.9)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Perplexity."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

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
        """Generate streaming response using Perplexity."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

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
