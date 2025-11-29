"""Hugging Face inference service."""

from typing import Dict, Any, AsyncGenerator
from ...base import ServiceType
from ...providers import HuggingFaceBaseService
from ...services import InferenceService

class HuggingFaceInferenceService(InferenceService, HuggingFaceBaseService):
    """Hugging Face inference service. Old: ~268 lines, New: ~70 lines, Reduction: 74%"""

    def __init__(self, config: Dict[str, Any]):
        HuggingFaceBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "huggingface")
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()
        try:
            response = await self.client.text_generation(
                prompt=prompt,
                temperature=kwargs.get('temperature', self.temperature),
                max_new_tokens=kwargs.get('max_tokens', self.max_tokens),
                **kwargs
            )
            return response
        except Exception as e:
            self._handle_huggingface_error(e, "generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        try:
            async for chunk in self.client.text_generation(
                prompt=prompt,
                temperature=kwargs.get('temperature', self.temperature),
                max_new_tokens=kwargs.get('max_tokens', self.max_tokens),
                stream=True,
                **kwargs
            ):
                yield chunk
        except Exception as e:
            self._handle_huggingface_error(e, "streaming")
            yield f"Error: {str(e)}"
