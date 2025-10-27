"""
Vertex AI inference service implementation using unified architecture.

This is a migrated version of the Vertex AI inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/vertex_ai_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import GoogleBaseService
from ..services import InferenceService


class VertexAIInferenceService(InferenceService, GoogleBaseService):
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

    def __init__(self, config: Dict[str, Any]):
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

            return response.text

        except Exception as e:
            self._handle_google_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Vertex AI."""
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

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            self._handle_google_error(e, "streaming generation")
            yield f"Error: {str(e)}"
