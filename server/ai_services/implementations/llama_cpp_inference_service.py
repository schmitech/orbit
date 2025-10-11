"""Llama.cpp inference service (embedded mode)."""

import os
import asyncio
from typing import Dict, Any, AsyncGenerator
from ..base import ServiceType, ProviderAIService
from ..services import InferenceService

class LlamaCppInferenceService(InferenceService, ProviderAIService):
    """Llama.cpp inference service using embedded mode. Old: ~321 lines, New: ~80 lines, Reduction: 75%"""

    def __init__(self, config: Dict[str, Any]):
        # Initialize via ProviderAIService first
        ProviderAIService.__init__(self, config, ServiceType.INFERENCE, "llama_cpp")
        
        # Get configuration
        provider_config = self._extract_provider_config()
        
        # Model configuration - use values from inference.yaml
        self.model_path = provider_config.get("model_path", "models/gemma-3-270m-it-Q8_0.gguf")
        self.chat_format = provider_config.get("chat_format", "gemma")
        self.n_ctx = provider_config.get("n_ctx", 2048)
        self.n_threads = provider_config.get("n_threads", 8)
        self.n_gpu_layers = provider_config.get("n_gpu_layers", 0)
        self.main_gpu = provider_config.get("main_gpu", 0)
        self.tensor_split = provider_config.get("tensor_split", None)
        self.repeat_penalty = provider_config.get("repeat_penalty", 1.2)
        
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
        
        # Model instance
        self.model = None
        
        # Suppress verbose output
        os.environ["LLAMA_CPP_VERBOSE"] = "0"
        os.environ["METAL_DEBUG_ERROR_MODE"] = "0"
        os.environ["GGML_METAL_SILENCE_INIT_LOGS"] = "1"

    async def initialize(self) -> bool:
        """Initialize the embedded Llama.cpp model."""
        if self.initialized:
            return True
            
        try:
            from llama_cpp import Llama
            
            if not self.model_path:
                self.logger.error("Llama.cpp model_path is required")
                return False
                
            if not os.path.exists(self.model_path):
                self.logger.error(f"Model file not found at: {self.model_path}")
                return False
            
            self.logger.info(f"Loading Llama.cpp model from: {self.model_path}")
            
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
            
            self.model = await asyncio.to_thread(_load_model)
            self.initialized = True
            self.logger.info("Llama.cpp model loaded successfully")
            return True
            
        except ImportError:
            self.logger.error("llama-cpp-python package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Llama.cpp model: {str(e)}")
            return False

    async def close(self) -> None:
        """Clean up the Llama.cpp model."""
        self.model = None
        self.initialized = False
        self.logger.debug("Llama.cpp model closed")

    async def verify_connection(self) -> bool:
        """Verify the model is loaded."""
        return self.model is not None

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
        """Generate response using embedded Llama.cpp."""
        if not self.initialized:
            await self.initialize()
            
        if not self.model:
            raise ValueError("Llama.cpp model not initialized")
            
        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)
            
            # Generate response in a thread
            def _generate():
                return self.model.create_chat_completion(
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
            self.logger.error(f"Error generating response with Llama.cpp: {str(e)}")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using embedded Llama.cpp."""
        if not self.initialized:
            await self.initialize()
            
        if not self.model:
            yield f"Error: Llama.cpp model not initialized"
            return
            
        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)
            
            # Generate streaming response in a thread
            def _stream_generate():
                return self.model.create_chat_completion(
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
            self.logger.error(f"Error generating streaming response with Llama.cpp: {str(e)}")
            yield f"Error: {str(e)}"
