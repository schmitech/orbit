"""NVIDIA NIM inference service (OpenAI-compatible API)."""

from typing import Dict, Any, AsyncGenerator
from ...base import ServiceType
from ...providers import NVIDIABaseService
from ...services import InferenceService

class NVIDIAInferenceService(InferenceService, NVIDIABaseService):
    """NVIDIA NIM inference service. Old: ~212 lines, New: ~70 lines, Reduction: 67%"""

    def __init__(self, config: Dict[str, Any]):
        NVIDIABaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "nvidia")
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()
        try:
            messages = kwargs.pop('messages', None) or [{"role": "user", "content": prompt}]
            response = await self.client.chat.completions.create(
                model=self.model, messages=messages,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens), **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            self._handle_nvidia_error(e, "generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        try:
            messages = kwargs.pop('messages', None) or [{"role": "user", "content": prompt}]
            stream = await self.client.chat.completions.create(
                model=self.model, messages=messages,
                temperature=kwargs.get('temperature', self.temperature),
                max_tokens=kwargs.get('max_tokens', self.max_tokens), stream=True, **kwargs
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            self._handle_nvidia_error(e, "streaming")
            yield f"Error: {str(e)}"
