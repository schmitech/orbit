"""
vLLM inference service implementation using unified architecture.

vLLM provides an OpenAI-compatible API, so we can use OpenAICompatibleBaseService.

Compare with: server/inference/pipeline/providers/vllm_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import OpenAICompatibleBaseService
from ..services import InferenceService


class VLLMInferenceService(InferenceService, OpenAICompatibleBaseService):
    """
    vLLM inference service using unified architecture.

    vLLM provides an OpenAI-compatible API for local model serving.

    Old implementation: ~398 lines (vllm_provider.py with quality controls)
    New implementation: ~100 lines
    Reduction: ~75%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the vLLM inference service."""
        # vLLM uses OpenAI-compatible API but typically on localhost
        OpenAICompatibleBaseService.__init__(self, config, ServiceType.INFERENCE, "vllm")
        InferenceService.__init__(self, config, "vllm")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using vLLM."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None) or [{"role": "user", "content": prompt}]

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
        """Generate streaming response using vLLM."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None) or [{"role": "user", "content": prompt}]

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
