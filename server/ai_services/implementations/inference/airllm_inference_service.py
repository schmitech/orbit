"""AirLLM local inference service.

Loads models locally via airllm.AutoModel, which offloads layers to run
large models under tight GPU/CPU memory budgets. AirLLM's generate() does
not support a token streamer, so generate_stream() runs generation to
completion and then chunks the result to simulate streaming.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers.airllm_base import AirLLMBaseService
from ...services import InferenceService

logger = logging.getLogger(__name__)


class AirLLMInferenceService(InferenceService, AirLLMBaseService):
    """Local AirLLM inference service for large models on limited memory."""

    def __init__(self, config: Dict[str, Any]):
        AirLLMBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "airllm")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=512)
        self.top_p = self._get_top_p(default=0.9)
        self.top_k = self._get_top_k(default=-1)
        self.stop_tokens = self._get_stop_tokens()

        provider_config = self._extract_provider_config()
        self.repetition_penalty = provider_config.get("repetition_penalty", 1.0)
        self.do_sample = provider_config.get("do_sample", True)

    async def validate_config(self) -> bool:
        """Skip API key check — local model needs no key."""
        try:
            if not self.model:
                logger.error("Model not configured")
                return False
            return await self.verify_connection()
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False

    def _format_messages_to_prompt(self, messages: list) -> str:
        """Format chat messages using the model's chat template."""
        if self.tokenizer and hasattr(self.tokenizer, 'apply_chat_template'):
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except Exception as e:
                logger.debug(f"Could not apply chat template: {e}")

        # Plain-text fallback
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    def _build_generate_kwargs(self, input_ids, **kwargs) -> dict:
        """Build kwargs dict for model.generate()."""
        temperature = kwargs.get("temperature", self.temperature)
        top_p = kwargs.get("top_p", self.top_p)
        top_k = kwargs.get("top_k", self.top_k)
        max_new_tokens = kwargs.get("max_tokens", self.max_tokens)
        repetition_penalty = kwargs.get("repetition_penalty", self.repetition_penalty)
        do_sample = kwargs.get("do_sample", self.do_sample)

        gen_kwargs: Dict[str, Any] = {
            "input_ids": input_ids,
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "repetition_penalty": repetition_penalty,
            "use_cache": True,
            "return_dict_in_generate": True,
        }

        if do_sample:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = top_p
            if top_k > 0:
                gen_kwargs["top_k"] = top_k

        return gen_kwargs

    def _run_generate(self, prompt_text: str, **kwargs) -> str:
        """Run AirLLM generation synchronously; called via asyncio.to_thread."""
        input_tokens = self.tokenizer(
            prompt_text,
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=self.max_seq_len,
            padding=False,
        )

        gen_kwargs = self._build_generate_kwargs(input_tokens["input_ids"], **kwargs)
        output = self.model_instance.generate(**gen_kwargs)

        return self.tokenizer.decode(
            output.sequences[0][input_tokens["input_ids"].shape[-1]:],
            skip_special_tokens=True,
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate a complete response (non-streaming)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop("messages", None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            prompt_text = self._format_messages_to_prompt(messages)
            return await asyncio.to_thread(self._run_generate, prompt_text, **kwargs)

        except Exception as e:
            self._handle_airllm_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Simulate streaming by chunking the completed generation.

        AirLLM's layer-offloaded generate() has no token streamer, so the
        full response is produced first and then yielded in chunks.
        """
        try:
            result = await self.generate(prompt, **kwargs)

            chunk_size = 10  # characters per chunk
            for i in range(0, len(result), chunk_size):
                yield result[i:i + chunk_size]
                await asyncio.sleep(0.01)  # Small delay for streaming effect

        except Exception:
            raise
