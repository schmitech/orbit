"""
Cohere inference service implementation using unified architecture.

This is a migrated version of the Cohere inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/cohere_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import CohereBaseService
from ..services import InferenceService


class CohereInferenceService(InferenceService, CohereBaseService):
    """
    Cohere inference service using unified architecture.

    Old implementation: ~267 lines (cohere_provider.py)
    New implementation: ~90 lines
    Reduction: ~66%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Cohere inference service."""
        # Initialize via InferenceService which will cooperate with CohereBaseService
        InferenceService.__init__(self, config, "cohere")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)

    def _get_temperature(self, default: float = 0.7) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 1024) -> int:
        """Get max_tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Cohere."""
        if not self.initialized:
            await self.initialize()

        try:
            response = await self.client.chat(
                model=self.model,
                message=prompt,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                p=kwargs.get('top_p', self.top_p),
                **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p']}
            )

            return response.text

        except Exception as e:
            self._handle_cohere_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Cohere."""
        if not self.initialized:
            await self.initialize()

        try:
            stream = self.client.chat_stream(
                model=self.model,
                message=prompt,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens),
                p=kwargs.get('top_p', self.top_p),
                **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens', 'top_p', 'stream']}
            )

            async for chunk in stream:
                if chunk.event_type == "text-generation":
                    yield chunk.text

        except Exception as e:
            self._handle_cohere_error(e, "streaming generation")
            yield f"Error: {str(e)}"
