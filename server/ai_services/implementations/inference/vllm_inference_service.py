"""
vLLM inference service implementation using unified architecture.

This service supports both API mode (OpenAI-compatible vLLM server)
and direct mode (in-process model loading with vLLM engine).

Compare with: server/inference/pipeline/providers/vllm_provider.py (old implementation)
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers.vllm_base import VLLMBaseService
from ...services import InferenceService


logger = logging.getLogger(__name__)


class VLLMInferenceService(InferenceService, VLLMBaseService):
    """
    vLLM inference service using unified architecture.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible vLLM server
    2. Direct mode: Loads models directly using vLLM engine (requires GPU)

    Old implementation: ~398 lines (vllm_provider.py with quality controls)
    New implementation: ~200 lines
    Reduction: ~50%
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the vLLM inference service."""
        # Cooperative initialization - VLLMBaseService handles mode detection
        super().__init__(config, "vllm")

        # Get generation parameters
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = self._get_top_k(default=-1)
        self.stop_tokens = self._get_stop_tokens()

        # Get additional parameters from config
        provider_config = self._extract_provider_config()
        self.repeat_penalty = provider_config.get("repetition_penalty", 1.0)
        self.presence_penalty = provider_config.get("presence_penalty", 0.0)
        self.frequency_penalty = provider_config.get("frequency_penalty", 0.0)

    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """Build messages in the format expected by vLLM."""
        if messages:
            return messages
        return [{"role": "user", "content": prompt}]

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using vLLM (API or direct mode)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)

            if self.mode == "api":
                return await self._generate_api(messages, **kwargs)
            else:
                return await self._generate_direct(messages, **kwargs)

        except Exception as e:
            self._handle_vllm_error(e, "text generation")
            raise

    async def _generate_api(self, messages: list, **kwargs) -> str:
        """Generate response using vLLM API mode."""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop('temperature', self.temperature),
            "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
            "top_p": kwargs.pop('top_p', self.top_p),
            "presence_penalty": kwargs.pop('presence_penalty', self.presence_penalty),
            "frequency_penalty": kwargs.pop('frequency_penalty', self.frequency_penalty),
            **kwargs
        }

        # Add stop tokens if configured
        if self.stop_tokens:
            params["stop"] = self.stop_tokens

        response = await self.client.chat.completions.create(**params)
        return response.choices[0].message.content

    async def _generate_direct(self, messages: list, **kwargs) -> str:
        """Generate response using vLLM direct mode."""
        if not self.vllm_engine:
            raise ValueError("vLLM engine not initialized")

        from vllm import SamplingParams

        # Build sampling parameters
        sampling_params = SamplingParams(
            temperature=kwargs.get('temperature', self.temperature),
            max_tokens=kwargs.get('max_tokens', self.max_tokens),
            top_p=kwargs.get('top_p', self.top_p),
            top_k=kwargs.get('top_k', self.top_k) if kwargs.get('top_k', self.top_k) > 0 else -1,
            repetition_penalty=kwargs.get('repetition_penalty', self.repeat_penalty),
            presence_penalty=kwargs.get('presence_penalty', self.presence_penalty),
            frequency_penalty=kwargs.get('frequency_penalty', self.frequency_penalty),
            stop=self.stop_tokens if self.stop_tokens else None,
        )

        # Format messages into a single prompt for vLLM
        prompt_text = self._format_messages_to_prompt(messages)

        # Generate in a thread to avoid blocking
        def _generate():
            outputs = self.vllm_engine.generate([prompt_text], sampling_params)
            return outputs[0].outputs[0].text

        result = await asyncio.to_thread(_generate)
        return result

    def _format_messages_to_prompt(self, messages: list) -> str:
        """Format chat messages into a single prompt string for vLLM."""
        # Try to use the model's chat template if available
        if self.vllm_engine:
            try:
                tokenizer = self.vllm_engine.get_tokenizer()
                if hasattr(tokenizer, 'apply_chat_template'):
                    return tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True
                    )
            except Exception as e:
                logger.debug(f"Could not apply chat template: {e}")

        # Fallback to simple formatting
        formatted_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_parts.append(f"System: {content}")
            elif role == "assistant":
                formatted_parts.append(f"Assistant: {content}")
            else:
                formatted_parts.append(f"User: {content}")

        formatted_parts.append("Assistant:")
        return "\n\n".join(formatted_parts)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using vLLM (API or direct mode)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)

            if self.mode == "api":
                async for chunk in self._generate_stream_api(messages, **kwargs):
                    yield chunk
            else:
                async for chunk in self._generate_stream_direct(messages, **kwargs):
                    yield chunk

        except Exception as e:
            self._handle_vllm_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    async def _generate_stream_api(self, messages: list, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using vLLM API mode."""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop('temperature', self.temperature),
            "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
            "top_p": kwargs.pop('top_p', self.top_p),
            "presence_penalty": kwargs.pop('presence_penalty', self.presence_penalty),
            "frequency_penalty": kwargs.pop('frequency_penalty', self.frequency_penalty),
            "stream": True,
            **kwargs
        }

        # Add stop tokens if configured
        if self.stop_tokens:
            params["stop"] = self.stop_tokens

        stream = await self.client.chat.completions.create(**params)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _generate_stream_direct(self, messages: list, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using vLLM direct mode."""
        if not self.vllm_engine:
            yield "Error: vLLM engine not initialized"
            return

        from vllm import SamplingParams

        # Build sampling parameters
        sampling_params = SamplingParams(
            temperature=kwargs.get('temperature', self.temperature),
            max_tokens=kwargs.get('max_tokens', self.max_tokens),
            top_p=kwargs.get('top_p', self.top_p),
            top_k=kwargs.get('top_k', self.top_k) if kwargs.get('top_k', self.top_k) > 0 else -1,
            repetition_penalty=kwargs.get('repetition_penalty', self.repeat_penalty),
            presence_penalty=kwargs.get('presence_penalty', self.presence_penalty),
            frequency_penalty=kwargs.get('frequency_penalty', self.frequency_penalty),
            stop=self.stop_tokens if self.stop_tokens else None,
        )

        # Format messages into a single prompt for vLLM
        prompt_text = self._format_messages_to_prompt(messages)

        # vLLM's LLM class doesn't support true streaming out of the box
        # For true streaming, you'd need to use the AsyncLLMEngine
        # For now, we generate the full response and yield it in chunks
        def _generate():
            outputs = self.vllm_engine.generate([prompt_text], sampling_params)
            return outputs[0].outputs[0].text

        result = await asyncio.to_thread(_generate)

        # Yield the result in chunks to simulate streaming
        chunk_size = 10  # characters per chunk
        for i in range(0, len(result), chunk_size):
            yield result[i:i + chunk_size]
            await asyncio.sleep(0.01)  # Small delay for streaming effect

    async def batch_generate(self, prompts: list, **kwargs) -> list:
        """
        Generate responses for multiple prompts (batch processing).

        This is particularly efficient in direct mode where vLLM can batch requests.
        """
        if not self.initialized:
            await self.initialize()

        if self.mode == "api":
            # API mode: process sequentially (or could be parallelized)
            results = []
            for prompt in prompts:
                result = await self.generate(prompt, **kwargs)
                results.append(result)
            return results
        else:
            # Direct mode: vLLM handles batching natively
            return await self._batch_generate_direct(prompts, **kwargs)

    async def _batch_generate_direct(self, prompts: list, **kwargs) -> list:
        """Batch generate using vLLM's native batching."""
        if not self.vllm_engine:
            raise ValueError("vLLM engine not initialized")

        from vllm import SamplingParams

        sampling_params = SamplingParams(
            temperature=kwargs.get('temperature', self.temperature),
            max_tokens=kwargs.get('max_tokens', self.max_tokens),
            top_p=kwargs.get('top_p', self.top_p),
            top_k=kwargs.get('top_k', self.top_k) if kwargs.get('top_k', self.top_k) > 0 else -1,
            repetition_penalty=kwargs.get('repetition_penalty', self.repeat_penalty),
            stop=self.stop_tokens if self.stop_tokens else None,
        )

        # Format all prompts
        formatted_prompts = []
        for prompt in prompts:
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = prompt
            formatted_prompts.append(self._format_messages_to_prompt(messages))

        # Generate all at once
        def _batch_generate():
            outputs = self.vllm_engine.generate(formatted_prompts, sampling_params)
            return [output.outputs[0].text for output in outputs]

        results = await asyncio.to_thread(_batch_generate)
        return results
