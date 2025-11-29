"""IBM Watson inference service."""

from typing import Dict, Any, AsyncGenerator
from ...base import ServiceType
from ...providers import WatsonBaseService
from ...services import InferenceService

class WatsonInferenceService(InferenceService, WatsonBaseService):
    """Watson inference service. Old: ~365 lines, New: ~70 lines, Reduction: 81%"""

    def __init__(self, config: Dict[str, Any]):
        WatsonBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "watson")
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()
        try:
            response = self.client.generate_text(
                prompt=prompt,
                params={
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_new_tokens": kwargs.get('max_tokens', self.max_tokens),
                    **kwargs
                }
            )
            return response
        except Exception as e:
            self._handle_watson_error(e, "generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        try:
            for chunk in self.client.generate_text_stream(
                prompt=prompt,
                params={
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_new_tokens": kwargs.get('max_tokens', self.max_tokens),
                    **kwargs
                }
            ):
                yield chunk
        except Exception as e:
            self._handle_watson_error(e, "streaming")
            yield f"Error: {str(e)}"
