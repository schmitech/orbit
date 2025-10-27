"""BitNet inference service for 1.58-bit LLM inference."""

import os
import asyncio
from typing import Dict, Any, AsyncGenerator
from ..base import ServiceType, ProviderAIService
from ..services import InferenceService
from ..providers.bitnet_base import BitNetBaseService


class BitNetInferenceService(InferenceService, BitNetBaseService):
    """BitNet inference service using 1.58-bit quantized models."""

    def __init__(self, config: Dict[str, Any]):
        # Initialize via ProviderAIService first
        ProviderAIService.__init__(self, config, ServiceType.INFERENCE, "bitnet")
        
        # Get configuration
        provider_config = self._extract_provider_config()
        
        # Model configuration - use values from inference.yaml
        self.model_path = provider_config.get("model_path", "models/bitnet-b1.58-3B/ggml-model-i2_s.gguf")
        self.quant_type = provider_config.get("quant_type", "i2_s")
        self.use_pretuned = provider_config.get("use_pretuned", True)
        self.quant_embd = provider_config.get("quant_embd", False)
        
        # Context and threading
        self.n_ctx = provider_config.get("n_ctx", 2048)
        self.n_threads = provider_config.get("n_threads", 8)
        self.n_batch = provider_config.get("n_batch", 2)
        
        # GPU settings
        self.n_gpu_layers = provider_config.get("n_gpu_layers", 0)
        self.main_gpu = provider_config.get("main_gpu", 0)
        self.low_vram = provider_config.get("low_vram", False)
        
        # Memory management
        self.use_mmap = provider_config.get("use_mmap", True)
        self.use_mlock = provider_config.get("use_mlock", False)
        
        # Kernel parameters
        self.kernel_params = provider_config.get("kernel_params", {})
        
        # Stop sequences
        self.stop_sequences = provider_config.get("stop", [])
        
        # Get inference-specific configuration from provider config
        self.temperature = provider_config.get("temperature", 0.7)
        self.max_tokens = provider_config.get("max_tokens", 1024)
        self.top_p = provider_config.get("top_p", 0.9)
        self.top_k = provider_config.get("top_k", 40)
        
        # Model instance
        self.model = None
        
        # Suppress verbose output
        os.environ["BITNET_VERBOSE"] = "0"

    async def initialize(self) -> bool:
        """Initialize the BitNet model."""
        if self.initialized:
            return True
            
        try:
            if self.mode == "direct":
                # Direct mode: Load model using BitNet Python bindings
                if not self.model_path:
                    self.logger.error("BitNet model_path is required for direct mode")
                    return False
                    
                if not os.path.exists(self.model_path):
                    self.logger.error(f"Model file not found at: {self.model_path}")
                    return False
                
                self.logger.info(f"Loading BitNet model from: {self.model_path}")
                
                # Load model in a thread to avoid blocking
                def _load_model():
                    from bitnet import BitNetInference
                    return BitNetInference(
                        model_path=self.model_path,
                        quant_type=self.quant_type,
                        use_pretuned=self.use_pretuned,
                        quant_embd=self.quant_embd,
                        n_ctx=self.n_ctx,
                        n_threads=self.n_threads,
                        n_batch=self.n_batch,
                        n_gpu_layers=self.n_gpu_layers,
                        main_gpu=self.main_gpu,
                        low_vram=self.low_vram,
                        use_mmap=self.use_mmap,
                        use_mlock=self.use_mlock,
                        kernel_params=self.kernel_params,
                        verbose=False
                    )
                
                self.model = await asyncio.to_thread(_load_model)
                self.logger.info("BitNet model loaded successfully")
                
            else:
                # API mode: Initialize OpenAI-compatible client
                from openai import AsyncOpenAI
                self.model = AsyncOpenAI(
                    api_key=self.api_key or "not-needed",
                    base_url=self.base_url
                )
                self.logger.info(f"BitNet API client initialized for {self.base_url}")
            
            self.initialized = True
            return True
            
        except ImportError:
            self.logger.error("BitNet package not installed. Please install with: pip install bitnet-cpp")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize BitNet model: {str(e)}")
            return False

    async def close(self) -> None:
        """Clean up the BitNet model."""
        if self.model and hasattr(self.model, 'close'):
            await self.model.close()
        self.model = None
        self.initialized = False
        self.logger.debug("BitNet model closed")

    async def verify_connection(self) -> bool:
        """Verify the model is loaded or API is accessible."""
        if self.mode == "api":
            try:
                if self.model:
                    # Try to list models or make a simple request
                    await self.model.models.list()
                    return True
            except Exception as e:
                self.logger.error(f"Failed to verify BitNet API connection: {str(e)}")
                return False
        else:
            return self.model is not None

    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """Build messages in the format expected by BitNet."""
        if messages:
            return messages
        return [{"role": "user", "content": prompt}]

    def _clean_response_text(self, text: str) -> str:
        """Clean up response text by removing special tokens."""
        if not text:
            return text
        
        # Clean up stop sequences
        for stop_seq in self.stop_sequences:
            text = text.replace(stop_seq, "")
        
        # Remove any trailing special tokens
        text = text.split("<")[0].strip()
        text = " ".join(text.split())
        return text

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using BitNet."""
        if not self.initialized:
            await self.initialize()
            
        if not self.model:
            raise ValueError("BitNet model not initialized")
            
        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)
            
            if self.mode == "direct":
                # Direct mode: Use BitNet Python bindings
                def _generate():
                    return self.model.generate(
                        prompt=prompt,
                        messages=messages,
                        temperature=kwargs.get("temperature", self.temperature),
                        top_p=kwargs.get("top_p", self.top_p),
                        top_k=kwargs.get("top_k", self.top_k),
                        max_tokens=kwargs.get("max_tokens", self.max_tokens),
                        stop=self.stop_sequences
                    )
                
                response = await asyncio.to_thread(_generate)
                
                # Extract and clean response text
                if isinstance(response, dict):
                    response_text = response.get("text", "")
                else:
                    response_text = str(response)
                    
                return self._clean_response_text(response_text)
                
            else:
                # API mode: Use OpenAI-compatible client
                response = await self.model.chat.completions.create(
                    model=self.model_name or "bitnet",
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    stop=self.stop_sequences if self.stop_sequences else None
                )
                
                # Extract and clean response text
                response_text = response.choices[0].message.content
                return self._clean_response_text(response_text)
                
        except Exception as e:
            self.logger.error(f"Error generating response with BitNet: {str(e)}")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using BitNet."""
        if not self.initialized:
            await self.initialize()
            
        if not self.model:
            yield f"Error: BitNet model not initialized"
            return
            
        try:
            messages = kwargs.pop('messages', None)
            messages = self._build_messages(prompt, messages)
            
            if self.mode == "direct":
                # Direct mode: Use BitNet Python bindings with streaming
                def _stream_generate():
                    return self.model.generate_stream(
                        prompt=prompt,
                        messages=messages,
                        temperature=kwargs.get("temperature", self.temperature),
                        top_p=kwargs.get("top_p", self.top_p),
                        top_k=kwargs.get("top_k", self.top_k),
                        max_tokens=kwargs.get("max_tokens", self.max_tokens),
                        stop=self.stop_sequences
                    )
                
                stream = await asyncio.to_thread(_stream_generate)
                
                # Process stream chunks
                for chunk in stream:
                    if chunk and isinstance(chunk, dict):
                        text = chunk.get("text", "")
                        if text:
                            # Clean up the text
                            text = self._clean_response_text(text)
                            if text:
                                yield text
                    elif chunk and isinstance(chunk, str):
                        text = self._clean_response_text(chunk)
                        if text:
                            yield text
                            
            else:
                # API mode: Use OpenAI-compatible streaming
                stream = await self.model.chat.completions.create(
                    model=self.model_name or "bitnet",
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    top_p=kwargs.get("top_p", self.top_p),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    stop=self.stop_sequences if self.stop_sequences else None,
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
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with BitNet: {str(e)}")
            yield f"Error: {str(e)}"
