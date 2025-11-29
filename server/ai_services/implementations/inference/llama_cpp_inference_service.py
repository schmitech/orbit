"""
Llama.cpp inference service implementation using unified architecture.

This service supports both API mode (OpenAI-compatible llama.cpp server)
and direct mode (embedded GGUF model loading with llama-cpp-python).

Compare with: server/ai_services/implementations/llama_cpp_embedding_service.py
"""

import logging
import os
import asyncio
from typing import Dict, Any, AsyncGenerator
from ...base import ServiceType
from ...services import InferenceService
from ...providers.llama_cpp_base import LlamaCppBaseService

logger = logging.getLogger(__name__)


class LlamaCppInferenceService(InferenceService, LlamaCppBaseService):
    """
    Llama.cpp inference service using unified architecture.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible llama.cpp server
    2. Direct mode: Loads GGUF models directly using llama-cpp-python
    """

    def __init__(self, config: Dict[str, Any]):
        # Cooperative initialization - LlamaCppBaseService handles mode detection
        super().__init__(config, "llama_cpp")

        # Get configuration
        provider_config = self._extract_provider_config()

        # Chat format (direct mode only)
        self.chat_format = provider_config.get("chat_format", "chatml")

        # Stop tokens
        self.stop_tokens = provider_config.get("stop_tokens", [
            "<start_of_turn>",
            "<end_of_turn>"
        ])

        # Get inference-specific configuration from provider config
        self.temperature = provider_config.get("temperature", 1.0)
        self.max_tokens = provider_config.get("max_tokens", 1024)
        self.top_p = provider_config.get("top_p", 0.95)
        self.top_k = provider_config.get("top_k", 64)
        self.repeat_penalty = provider_config.get("repeat_penalty", 1.2)

        # Suppress verbose output
        os.environ["LLAMA_CPP_VERBOSE"] = "0"
        os.environ["METAL_DEBUG_ERROR_MODE"] = "0"
        os.environ["GGML_METAL_SILENCE_INIT_LOGS"] = "1"

    async def initialize(self) -> bool:
        """Initialize the Llama.cpp model (API or direct mode)."""
        if self.initialized:
            return True

        try:
            if self.mode == "direct":
                # Direct mode: Load GGUF model with llama-cpp-python
                from llama_cpp import Llama

                if not self.model_path:
                    logger.error("Llama.cpp model_path is required for direct mode")
                    return False

                if not os.path.exists(self.model_path):
                    logger.error(f"Model file not found at: {self.model_path}")
                    return False

                logger.info(f"Loading Llama.cpp model from: {self.model_path}")

                # Load model in a thread to avoid blocking
                def _load_model():
                    return Llama(
                        model_path=self.model_path,
                        n_ctx=self.n_ctx,
                        n_threads=self.n_threads,
                        chat_format=self.chat_format,
                        verbose=False,
                        n_gpu_layers=self.n_gpu_layers,
                        main_gpu=self.main_gpu,
                        tensor_split=self.tensor_split,
                        stop=self.stop_tokens,
                        repeat_penalty=self.repeat_penalty
                    )

                self.llama_model = await asyncio.to_thread(_load_model)
                logger.info("Llama.cpp model loaded successfully")

            else:
                # API mode: Already initialized by LlamaCppBaseService
                logger.info(f"Llama.cpp API mode configured at {self.base_url}")

            self.initialized = True
            return True

        except ImportError:
            logger.error("llama-cpp-python package not installed (required for direct mode)")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Llama.cpp: {str(e)}")
            return False

    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """Build messages in the format expected by Llama.cpp."""
        if messages:
            return messages
        return [{"role": "user", "content": prompt}]

    def _clean_response_text(self, text: str) -> str:
        """Clean up response text by removing special tokens."""
        if not text:
            return text
        
        # Clean up stop tokens
        for token in self.stop_tokens:
            text = text.replace(token, "")
        
        # Remove any trailing special tokens
        text = text.split("<")[0].strip()
        text = " ".join(text.split())
        return text

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Llama.cpp (API or direct mode)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)

            if self.mode == "api":
                # API mode: Use OpenAI-compatible client
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    stop=self.stop_tokens if self.stop_tokens else None
                )

                # Extract and clean response text
                response_text = response.choices[0].message.content
                return self._clean_response_text(response_text)

            else:
                # Direct mode: Use llama-cpp-python
                if not self.llama_model:
                    raise ValueError("Llama.cpp model not initialized")

                # Generate response in a thread
                def _generate():
                    return self.llama_model.create_chat_completion(
                        messages=messages,
                        temperature=kwargs.get("temperature", self.temperature),
                        top_p=kwargs.get("top_p", self.top_p),
                        top_k=kwargs.get("top_k", self.top_k),
                        max_tokens=kwargs.get("max_tokens", self.max_tokens),
                        stop=self.stop_tokens,
                        repeat_penalty=self.repeat_penalty
                    )

                response = await asyncio.to_thread(_generate)

                # Extract and clean response text
                response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._clean_response_text(response_text)

        except Exception as e:
            logger.error(f"Error generating response with Llama.cpp: {str(e)}")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Llama.cpp (API or direct mode)."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)

            if self.mode == "api":
                # API mode: Use OpenAI-compatible streaming
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    stop=self.stop_tokens if self.stop_tokens else None,
                    stream=True
                )

                # Process stream chunks
                async for chunk in stream:
                    if chunk and chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        if choice.delta and choice.delta.content:
                            text = choice.delta.content
                            if text:
                                # Clean up the text
                                text = self._clean_response_text(text)
                                if text:
                                    yield text

            else:
                # Direct mode: Use llama-cpp-python
                if not self.llama_model:
                    yield "Error: Llama.cpp model not initialized"
                    return

                # Generate streaming response in a thread
                def _stream_generate():
                    return self.llama_model.create_chat_completion(
                        messages=messages,
                        temperature=kwargs.get("temperature", self.temperature),
                        top_p=kwargs.get("top_p", self.top_p),
                        top_k=kwargs.get("top_k", self.top_k),
                        max_tokens=kwargs.get("max_tokens", self.max_tokens),
                        stream=True,
                        stop=self.stop_tokens,
                        repeat_penalty=self.repeat_penalty
                    )

                stream = await asyncio.to_thread(_stream_generate)

                # Process stream chunks
                for chunk in stream:
                    if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                        choice = chunk["choices"][0]
                        if "delta" in choice and "content" in choice["delta"]:
                            text = choice["delta"]["content"]
                            if text:
                                # Clean up the text
                                text = self._clean_response_text(text)
                                if text:
                                    yield text

        except Exception as e:
            logger.error(f"Error generating streaming response with Llama.cpp: {str(e)}")
            yield f"Error: {str(e)}"
