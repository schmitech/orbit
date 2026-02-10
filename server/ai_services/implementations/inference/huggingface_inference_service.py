"""Hugging Face inference service using unified architecture.

Uses the huggingface_hub AsyncInferenceClient chat_completion API,
which mirrors the OpenAI chat completions interface.
"""

from typing import Dict, Any, AsyncGenerator
import logging

from ...base import ServiceType
from ...providers import HuggingFaceBaseService
from ...services import InferenceService

logger = logging.getLogger(__name__)


class HuggingFaceInferenceService(InferenceService, HuggingFaceBaseService):
    """Hugging Face inference service using the chat completions API."""

    def __init__(self, config: Dict[str, Any]):
        HuggingFaceBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "huggingface")
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            params = {
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                "stream": False,
            }

            stop = kwargs.pop('stop', None)
            if stop:
                params["stop"] = stop

            logger.debug(f"HuggingFace generate: model={self.model}, max_tokens={params['max_tokens']}")
            response = await self.client.chat_completion(**params)

            if not response.choices:
                logger.warning("HuggingFace returned response with no choices")
                return ""

            content = response.choices[0].message.content
            logger.debug(f"HuggingFace generate: received {len(content or '')} chars")
            return content or ""

        except RuntimeError as e:
            if "StopIteration" in str(e):
                raise ValueError("Hugging Face returned an empty response") from e
            self._handle_huggingface_error(e, "generation")
            raise
        except Exception as e:
            self._handle_huggingface_error(e, "generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            params = {
                "messages": messages,
                "temperature": kwargs.pop('temperature', self.temperature),
                "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                "top_p": kwargs.pop('top_p', self.top_p),
                "stream": True,
            }

            stop = kwargs.pop('stop', None)
            if stop:
                params["stop"] = stop

            logger.debug(f"HuggingFace stream: model={self.model}, max_tokens={params['max_tokens']}")
            stream = await self.client.chat_completion(**params)

            # Iterate using __anext__ directly to avoid PEP 479 StopIteration
            # issues inside this async generator. The HF client's async iterator
            # can leak StopIteration from internal sync iteration, which Python
            # converts to RuntimeError inside async generators.
            chunk_count = 0
            aiter = stream.__aiter__()
            while True:
                try:
                    chunk = await aiter.__anext__()
                except StopAsyncIteration:
                    break
                chunk_count += 1
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            if chunk_count == 0:
                logger.warning("HuggingFace stream returned zero chunks — check model availability and provider setting")
            else:
                logger.debug(f"HuggingFace stream complete: {chunk_count} chunks")

        except RuntimeError as e:
            if "StopIteration" in str(e):
                # PEP 479: StopIteration inside a coroutine becomes RuntimeError.
                # This can happen when the HF client's internal sync iterators
                # are exhausted inside an async context. Treat as normal end-of-stream.
                return
            self._handle_huggingface_error(e, "streaming")
            raise
        except Exception as e:
            self._handle_huggingface_error(e, "streaming")
            raise
