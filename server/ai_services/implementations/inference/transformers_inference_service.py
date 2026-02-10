"""Transformers local inference service with true token-level streaming.

Loads HuggingFace models locally via AutoModelForCausalLM and generates
text using model.generate(). Streaming uses TextIteratorStreamer to yield
tokens as they are decoded, rather than faking streaming after full generation.
"""

import logging
import asyncio
from threading import Thread
from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers.transformers_base import TransformersBaseService
from ...services import InferenceService

logger = logging.getLogger(__name__)


class _StreamError:
    """Sentinel that carries an exception from the generation thread."""
    def __init__(self, exc: Exception):
        self.exc = exc


class TransformersInferenceService(InferenceService, TransformersBaseService):
    """
    Local Transformers inference service with true token-level streaming.

    Uses TextIteratorStreamer so each decoded token is yielded as it is
    produced by model.generate(), rather than generating the full response
    first and chunking it.
    """

    def __init__(self, config: Dict[str, Any]):
        TransformersBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "transformers")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
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
        }

        if do_sample:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = top_p
            if top_k > 0:
                gen_kwargs["top_k"] = top_k

        if self.tokenizer.eos_token_id is not None:
            gen_kwargs["eos_token_id"] = self.tokenizer.eos_token_id
        if self.tokenizer.pad_token_id is not None:
            gen_kwargs["pad_token_id"] = self.tokenizer.pad_token_id

        return gen_kwargs

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate a complete response (non-streaming)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop("messages", None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            prompt_text = self._format_messages_to_prompt(messages)

            def _run():
                inputs = self.tokenizer(prompt_text, return_tensors="pt")
                input_ids = inputs["input_ids"].to(self.model_instance.device)
                input_len = input_ids.shape[-1]

                gen_kwargs = self._build_generate_kwargs(input_ids, **kwargs)
                output_ids = self.model_instance.generate(**gen_kwargs)

                # Decode only newly generated tokens
                new_tokens = output_ids[0][input_len:]
                return self.tokenizer.decode(new_tokens, skip_special_tokens=True)

            result = await asyncio.to_thread(_run)
            return result

        except Exception as e:
            self._handle_transformers_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate a streaming response using TextIteratorStreamer."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop("messages", None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            prompt_text = self._format_messages_to_prompt(messages)

            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def _generation_worker():
                """Runs in a background thread: sets up streamer, launches generate."""
                try:
                    from transformers import TextIteratorStreamer

                    inputs = self.tokenizer(prompt_text, return_tensors="pt")
                    input_ids = inputs["input_ids"].to(self.model_instance.device)

                    streamer = TextIteratorStreamer(
                        self.tokenizer,
                        skip_prompt=True,
                        skip_special_tokens=True,
                    )

                    gen_kwargs = self._build_generate_kwargs(input_ids, **kwargs)
                    gen_kwargs["streamer"] = streamer

                    # model.generate blocks, so run it in a daemon thread
                    gen_thread = Thread(
                        target=self.model_instance.generate,
                        kwargs=gen_kwargs,
                        daemon=True,
                    )
                    gen_thread.start()

                    # Iterate the streamer (blocks until each token is ready)
                    for text in streamer:
                        if text:
                            loop.call_soon_threadsafe(queue.put_nowait, text)

                    gen_thread.join()

                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, _StreamError(exc))
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

            # Launch the worker in the executor
            asyncio.ensure_future(
                loop.run_in_executor(self.executor, _generation_worker)
            )

            # Yield tokens as they arrive
            while True:
                token = await queue.get()
                if token is None:
                    break
                if isinstance(token, _StreamError):
                    self._handle_transformers_error(token.exc, "streaming generation")
                    raise token.exc
                yield token

        except Exception as e:
            if not isinstance(e, (StopAsyncIteration,)):
                self._handle_transformers_error(e, "streaming generation")
            yield f"Error: {e}"
