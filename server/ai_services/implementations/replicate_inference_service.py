"""Replicate inference service."""

from typing import Dict, Any, AsyncGenerator
from ..base import ServiceType
from ..providers import ReplicateBaseService
from ..services import InferenceService

class ReplicateInferenceService(InferenceService, ReplicateBaseService):
    """Replicate inference service. Old: ~213 lines, New: ~65 lines, Reduction: 69%"""

    def __init__(self, config: Dict[str, Any]):
        ReplicateBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "replicate")
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()
        try:
            output = await self.client.async_run(
                self.model,
                input={
                    "prompt": prompt,
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_tokens": kwargs.get('max_tokens', self.max_tokens),
                    **kwargs
                }
            )
            return "".join(output) if isinstance(output, list) else str(output)
        except Exception as e:
            self._handle_replicate_error(e, "generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()
        try:
            async for chunk in self.client.async_stream(
                self.model,
                input={
                    "prompt": prompt,
                    "temperature": kwargs.get('temperature', self.temperature),
                    "max_tokens": kwargs.get('max_tokens', self.max_tokens),
                    **kwargs
                }
            ):
                yield str(chunk)
        except Exception as e:
            self._handle_replicate_error(e, "streaming")
            yield f"Error: {str(e)}"
