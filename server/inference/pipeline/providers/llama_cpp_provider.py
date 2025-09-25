"""
Llama.cpp Provider for Pipeline Architecture

This module provides a clean Llama.cpp implementation for the pipeline architecture.
"""

import os
import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

# Suppress Metal/OpenCL initialization messages
os.environ["LLAMA_CPP_VERBOSE"] = "0"
os.environ["METAL_DEBUG_ERROR_MODE"] = "0"  
os.environ["METAL_DEVICE_WRAPPER_TYPE"] = "0"
os.environ["METAL_DEBUG_OPTIONS"] = "silent"
os.environ["GGML_METAL_SILENCE_INIT_LOGS"] = "1"
os.environ["GGML_METAL_VERBOSE"] = "0"
os.environ["OPENCL_LOG_LEVEL"] = "0"
os.environ["GGML_SILENT"] = "1"
os.environ["GGML_VERBOSE"] = "0"
os.environ["GGML_DEBUG"] = "0"
os.environ["GGML_METAL_DEBUG"] = "0"

class LlamaCppProvider(LLMProvider):
    """
    Clean Llama.cpp implementation for the pipeline architecture.
    
    This provider uses llama-cpp-python for local model inference without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Llama.cpp provider.
        
        Args:
            config: Configuration dictionary containing Llama.cpp settings
        """
        self.config = config
        llama_cpp_config = config.get("inference", {}).get("llama_cpp", {})
        
        self.model_path = llama_cpp_config.get("model_path", "")
        self.chat_format = llama_cpp_config.get("chat_format", None)
        self.temperature = llama_cpp_config.get("temperature", 0.1)
        self.top_p = llama_cpp_config.get("top_p", 0.8)
        self.top_k = llama_cpp_config.get("top_k", 20)
        self.max_tokens = llama_cpp_config.get("max_tokens", 512)
        self.n_ctx = llama_cpp_config.get("n_ctx", 4096)
        self.n_threads = llama_cpp_config.get("n_threads", 4)
        self.stream = llama_cpp_config.get("stream", True)
        
        # GPU-related parameters
        self.n_gpu_layers = llama_cpp_config.get("n_gpu_layers", -1)
        self.main_gpu = llama_cpp_config.get("main_gpu", 0)
        self.tensor_split = llama_cpp_config.get("tensor_split", None)
        
        # Stop tokens and repetition penalty
        self.stop_tokens = llama_cpp_config.get("stop_tokens", [
            "<|im_start|>", "<|file_ref_name|>", "<|file_ref>", "<|file_name|>",
            "<|im_end|>", "</im_end|>", "<im_end>", "</im_end>",
            "</s>", "<|endoftext|>", "<|system_prompt|>",
            "<|file_ref|>system_prompt", "<|im_start|>"
        ])
        self.repeat_penalty = llama_cpp_config.get("repeat_penalty", 1.1)
        
        self.model = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Llama.cpp model."""
        try:
            from llama_cpp import Llama
            
            if not self.model_path:
                raise ValueError("Llama.cpp model_path is required")
            
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found at: {self.model_path}")
            
            if self.verbose:
                self.logger.info(f"Loading model from: {self.model_path}")
            
            # Load model in a thread to avoid blocking
            def _load_model():
                return Llama(
                    model_path=self.model_path,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    chat_format=self.chat_format,
                    verbose=False,  # Always set to False to suppress output
                    n_gpu_layers=self.n_gpu_layers,
                    main_gpu=self.main_gpu,
                    tensor_split=self.tensor_split,
                    stop=self.stop_tokens,
                    repeat_penalty=self.repeat_penalty
                )
            
            self.model = await asyncio.to_thread(_load_model)
            self.logger.info("Initialized Llama.cpp provider successfully")
            
        except ImportError:
            self.logger.error("llama-cpp-python package not installed. Please install with: pip install llama-cpp-python")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Llama.cpp model: {str(e)}")
            raise
    
    def _clean_response_text(self, text: str) -> str:
        """
        Clean up response text by removing special tokens and artifacts.
        
        Args:
            text: Raw response text from the model
            
        Returns:
            Cleaned response text
        """
        if not text:
            return text
        
        # Clean up any remaining file reference tags and system tags
        cleanup_patterns = [
            "<|file_ref_name|>", "<|file_ref>", "<|file_name|>",
            "<|im_end|>", "</im_end|>", "<im_end>", "</im_end>",
            "<|system_prompt|>", "<|file_ref|>system_prompt",
            "<|im_start|>", "</im_start|>", "<im_start>", "</im_start>"
        ]
        
        # Clean up any pattern that appears anywhere in the response
        for pattern in cleanup_patterns:
            text = text.replace(pattern, "")
        
        # Remove any trailing special tokens or incomplete tags
        text = text.split("<")[0].strip()
        
        # Remove any remaining whitespace artifacts
        text = " ".join(text.split())
        
        return text
    
    def _build_messages(self, prompt: str, messages: list = None) -> list:
        """
        Build messages in the format expected by Llama.cpp.
        
        Args:
            prompt: The input prompt
            messages: Optional pre-formatted messages list
            
        Returns:
            List of message dictionaries
        """
        if messages:
            return messages

        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                messages = []
                if system_part:
                    messages.append({"role": "system", "content": system_part})
                messages.append({"role": "user", "content": user_part})
                return messages
        
        # If no clear separation, treat entire prompt as user message
        return [{"role": "user", "content": prompt}]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Llama.cpp.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)
            
        Returns:
            The generated response text
        """
        if not self.model:
            await self.initialize()
        
        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            # Build messages
            messages = self._build_messages(prompt, messages)
            
            if self.verbose:
                self.logger.debug(f"Generating with Llama.cpp: temperature={self.temperature}, max_tokens={self.max_tokens}")
            
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
            
            # Extract response text
            response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Clean up the response
            response_text = self._clean_response_text(response_text)
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with Llama.cpp: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Llama.cpp.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)
            
        Yields:
            Response chunks as they are generated
        """
        if not self.model:
            await self.initialize()
        
        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            # Build messages
            messages = self._build_messages(prompt, messages)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Llama.cpp")
            
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
                            # Skip chunks that match stop tokens
                            if any(token in text for token in self.stop_tokens):
                                continue
                                
                            # Strip out any stray stop-token emissions entirely
                            if text.strip() in self.stop_tokens:
                                continue

                            # Remove stop-token substrings but leave llama.cpp's leading space
                            for pattern in self.stop_tokens:
                                text = text.replace(pattern, "")

                            # Truncate at any control-token boundary
                            text = text.split("<")[0]

                            if text:
                                yield text
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Llama.cpp: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Llama.cpp model."""
        # Llama.cpp model doesn't need explicit cleanup
        self.model = None
        self.logger.info("Llama.cpp provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Llama.cpp configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.model_path:
                self.logger.error("Llama.cpp model_path is missing")
                return False
            
            if not os.path.exists(self.model_path):
                self.logger.error(f"Model file not found at: {self.model_path}")
                return False
            
            # Test model loading
            if not self.model:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Llama.cpp configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("llama-cpp-python package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Llama.cpp configuration validation failed: {str(e)}")
            return False