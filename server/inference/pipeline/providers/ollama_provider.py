"""
Ollama Provider for Pipeline Architecture

This module provides a clean Ollama implementation for the pipeline architecture.
"""

import json
import logging
import time
from typing import Dict, Any, AsyncGenerator, Optional
import aiohttp
from .llm_provider import LLMProvider
from utils.ollama_utils import OllamaBaseService, OllamaConfig


class OllamaProvider(LLMProvider, OllamaBaseService):
    """
    Clean Ollama implementation for the pipeline architecture.
    
    This provider communicates directly with Ollama's API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama provider.
        
        Args:
            config: Configuration dictionary containing Ollama settings
        """
        # Initialize base service
        OllamaBaseService.__init__(self, config, 'inference')
        
        # Get Ollama specific configuration
        ollama_config = config.get('inference', {}).get('ollama', {})
        if not ollama_config:
            ollama_config = config.get('ollama', {})  # Backward compatibility
        
        # Additional inference-specific settings
        self.top_p = ollama_config.get('top_p', 0.8)
        self.top_k = ollama_config.get('top_k', 20)
        self.min_p = ollama_config.get('min_p', 0.0)
        self.typical_p = ollama_config.get('typical_p', 0.7)
        self.repeat_penalty = ollama_config.get('repeat_penalty', 1.1)
        self.repeat_last_n = ollama_config.get('repeat_last_n', 33)
        self.presence_penalty = ollama_config.get('presence_penalty', 0.0)
        self.frequency_penalty = ollama_config.get('frequency_penalty', 0.0)
        self.num_predict = ollama_config.get('num_predict', 1024)
        self.num_ctx = ollama_config.get('num_ctx', 8192)
        self.num_keep = ollama_config.get('num_keep', 5)
        self.penalize_newline = ollama_config.get('penalize_newline', False)
        self.stop = ollama_config.get('stop', [])
        self.num_batch = ollama_config.get('num_batch', 2)
        self.num_gpu = ollama_config.get('num_gpu', 0)
        self.main_gpu = ollama_config.get('main_gpu', 0)
        self.low_vram = ollama_config.get('low_vram', False)
        self.use_mmap = ollama_config.get('use_mmap', True)
        self.use_mlock = ollama_config.get('use_mlock', False)
        self.vocab_only = ollama_config.get('vocab_only', False)
        self.numa = ollama_config.get('numa', False)
        self.seed = ollama_config.get('seed')
        # Mirostat sampling
        self.mirostat = ollama_config.get('mirostat', 0)
        self.mirostat_tau = ollama_config.get('mirostat_tau', 0.8)
        self.mirostat_eta = ollama_config.get('mirostat_eta', 0.6)
        self.stream = ollama_config.get('stream', True)
    
    async def initialize(self, clock_service: Optional[Any] = None) -> None:
        """Initialize the Ollama provider."""
        success = await OllamaBaseService.initialize(self, warmup_endpoint='generate')
        if not success:
            raise RuntimeError(f"Failed to initialize Ollama provider with model {self.config.model}")
    
    async def close(self) -> None:
        """Clean up the Ollama provider."""
        await OllamaBaseService.close(self)
        self.logger.info("Ollama provider cleanup completed")
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Ollama with retry logic.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        async def _generate():
            start_time = time.time()

            # Extract messages if provided
            messages = kwargs.pop('messages', None)

            # Check if model uses chat format (OpenAI-compatible models)
            use_chat_api = self.config.model.startswith('gpt-') or 'openai' in self.config.model.lower()

            session = await self.session_manager.get_session()

            if use_chat_api or messages:
                # Use chat endpoint for OpenAI-compatible models
                options = {
                    "temperature": self.config.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "min_p": self.min_p,
                    "typical_p": self.typical_p,
                    "repeat_penalty": self.repeat_penalty,
                    "repeat_last_n": self.repeat_last_n,
                    "presence_penalty": self.presence_penalty,
                    "frequency_penalty": self.frequency_penalty,
                    "mirostat": self.mirostat,
                    "mirostat_tau": self.mirostat_tau,
                    "mirostat_eta": self.mirostat_eta,
                    "num_ctx": self.num_ctx,
                    "num_keep": self.num_keep,
                    "penalize_newline": self.penalize_newline,
                    "num_batch": self.num_batch,
                    "num_gpu": self.num_gpu,
                    "main_gpu": self.main_gpu,
                    "low_vram": self.low_vram,
                    "use_mmap": self.use_mmap,
                    "use_mlock": self.use_mlock,
                    "vocab_only": self.vocab_only,
                    "numa": self.numa,
                }
                
                # Add seed if specified
                if self.seed is not None:
                    options["seed"] = self.seed
                
                # Filter out None values
                options = {k: v for k, v in options.items() if v is not None}
                
                # Use messages if provided, otherwise convert prompt to message format
                if messages is None:
                    messages = [{"role": "user", "content": prompt}]

                async with session.post(
                    f"{self.config.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "messages": messages,
                        "stream": False,
                        "options": options,
                        "stop": self.stop if self.stop else None,
                        **kwargs
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        raise Exception(f"Failed to generate response: {error_text}")
                    
                    data = await response.json()
                    response_text = data.get("message", {}).get("content", "")
            else:
                # Use generate endpoint for traditional Ollama models
                options = {
                    "temperature": self.config.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "min_p": self.min_p,
                    "typical_p": self.typical_p,
                    "repeat_penalty": self.repeat_penalty,
                    "repeat_last_n": self.repeat_last_n,
                    "presence_penalty": self.presence_penalty,
                    "frequency_penalty": self.frequency_penalty,
                    "mirostat": self.mirostat,
                    "mirostat_tau": self.mirostat_tau,
                    "mirostat_eta": self.mirostat_eta,
                    "num_ctx": self.num_ctx,
                    "num_keep": self.num_keep,
                    "penalize_newline": self.penalize_newline,
                    "num_batch": self.num_batch,
                    "num_gpu": self.num_gpu,
                    "main_gpu": self.main_gpu,
                    "low_vram": self.low_vram,
                    "use_mmap": self.use_mmap,
                    "use_mlock": self.use_mlock,
                    "vocab_only": self.vocab_only,
                    "numa": self.numa,
                }
                
                # Add seed if specified
                if self.seed is not None:
                    options["seed"] = self.seed
                
                # Filter out None values
                options = {k: v for k, v in options.items() if v is not None}
                
                async with session.post(
                    f"{self.config.base_url}/api/generate",
                    json={
                        "model": self.config.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": options,
                        "stop": self.stop if self.stop else None,
                        **kwargs
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Ollama error: {error_text}")
                        raise Exception(f"Failed to generate response: {error_text}")
                    
                    data = await response.json()
                    response_text = data.get("response", "")
                
            processing_time = time.time() - start_time
            if self.config.verbose:
                self.logger.info(f"Ollama generation completed in {processing_time:.3f}s")
            
            return response_text
        
        try:
            return await self.retry_handler.execute_with_retry(_generate)
        except Exception as e:
            self.logger.error(f"Error generating response with Ollama: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama with retry logic.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        retries = 0
        last_exception = None

        while retries < self.config.max_retries if self.config.retry_enabled else retries == 0:
            try:
                # Extract messages if provided
                messages = kwargs.pop('messages', None)

                # Check if model uses chat format (OpenAI-compatible models)
                use_chat_api = self.config.model.startswith('gpt-') or 'openai' in self.config.model.lower()

                session = await self.session_manager.get_session()

                if use_chat_api or messages:
                    # Use chat endpoint for OpenAI-compatible models
                    options = {
                        "temperature": self.config.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "min_p": self.min_p,
                        "typical_p": self.typical_p,
                        "repeat_penalty": self.repeat_penalty,
                        "repeat_last_n": self.repeat_last_n,
                        "presence_penalty": self.presence_penalty,
                        "frequency_penalty": self.frequency_penalty,
                        "mirostat": self.mirostat,
                        "mirostat_tau": self.mirostat_tau,
                        "mirostat_eta": self.mirostat_eta,
                        "num_ctx": self.num_ctx,
                        "num_keep": self.num_keep,
                        "penalize_newline": self.penalize_newline,
                        "num_batch": self.num_batch,
                        "num_gpu": self.num_gpu,
                        "main_gpu": self.main_gpu,
                        "low_vram": self.low_vram,
                        "use_mmap": self.use_mmap,
                        "use_mlock": self.use_mlock,
                        "vocab_only": self.vocab_only,
                        "numa": self.numa,
                    }
                    
                    # Add seed if specified
                    if self.seed is not None:
                        options["seed"] = self.seed
                    
                    # Filter out None values
                    options = {k: v for k, v in options.items() if v is not None}
                    
                    # Use messages if provided, otherwise convert prompt to message format
                    if messages is None:
                        messages = [{"role": "user", "content": prompt}]

                    async with session.post(
                        f"{self.config.base_url}/api/chat",
                        json={
                            "model": self.config.model,
                            "messages": messages,
                            "stream": True,
                            "options": options,
                            "stop": self.stop if self.stop else None,
                            **kwargs
                        }
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            self.logger.error(f"Ollama error: {error_text}")
                            yield f"Error: Failed to generate response: {error_text}"
                            return
                        
                        # Parse the streaming response
                        async for line in response.content:
                            chunk = line.decode('utf-8').strip()
                            if not chunk:
                                continue
                            
                            try:
                                data = json.loads(chunk)
                                if "message" in data:
                                    content = data["message"].get("content", "")
                                    if content:
                                        yield content
                                
                                if data.get("done", False):
                                    break
                                    
                            except json.JSONDecodeError:
                                self.logger.error(f"Error parsing JSON: {chunk}")
                                continue
                else:
                    # Use generate endpoint for traditional Ollama models
                    options = {
                        "temperature": self.config.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "min_p": self.min_p,
                        "typical_p": self.typical_p,
                        "repeat_penalty": self.repeat_penalty,
                        "repeat_last_n": self.repeat_last_n,
                        "presence_penalty": self.presence_penalty,
                        "frequency_penalty": self.frequency_penalty,
                        "mirostat": self.mirostat,
                        "mirostat_tau": self.mirostat_tau,
                        "mirostat_eta": self.mirostat_eta,
                        "num_ctx": self.num_ctx,
                        "num_keep": self.num_keep,
                        "penalize_newline": self.penalize_newline,
                        "num_batch": self.num_batch,
                        "num_gpu": self.num_gpu,
                        "main_gpu": self.main_gpu,
                        "low_vram": self.low_vram,
                        "use_mmap": self.use_mmap,
                        "use_mlock": self.use_mlock,
                        "vocab_only": self.vocab_only,
                        "numa": self.numa,
                    }
                    
                    # Add seed if specified
                    if self.seed is not None:
                        options["seed"] = self.seed
                    
                    # Filter out None values
                    options = {k: v for k, v in options.items() if v is not None}
                    
                    async with session.post(
                        f"{self.config.base_url}/api/generate",
                        json={
                            "model": self.config.model,
                            "prompt": prompt,
                            "stream": True,
                            "options": options,
                            "stop": self.stop if self.stop else None,
                            **kwargs
                        }
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            self.logger.error(f"Ollama error: {error_text}")
                            yield f"Error: Failed to generate response: {error_text}"
                            return
                        
                        # Parse the streaming response
                        async for line in response.content:
                            chunk = line.decode('utf-8').strip()
                            if not chunk:
                                continue
                            
                            try:
                                data = json.loads(chunk)
                                if "response" in data:
                                    yield data["response"]
                                
                                if data.get("done", False):
                                    break
                                    
                            except json.JSONDecodeError:
                                self.logger.error(f"Error parsing JSON: {chunk}")
                                continue
                
                # If we get here, streaming completed successfully
                return
                            
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check if it's a retryable error
                if self.config.retry_enabled and any(x in error_msg for x in ['timeout', 'connection', 'refused', 'reset']):
                    wait_time = min(
                        self.config.initial_wait_ms * (self.config.exponential_base ** retries),
                        self.config.max_wait_ms
                    ) / 1000
                    
                    if retries < self.config.max_retries - 1:
                        self.logger.warning(
                            f"Streaming attempt {retries + 1}/{self.config.max_retries} failed: {str(e)}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        import asyncio
                        await asyncio.sleep(wait_time)
                        retries += 1
                        continue
                
                # Non-retryable error or max retries reached
                self.logger.error(f"Error generating streaming response with Ollama: {str(e)}")
                yield f"Error: {str(e)}"
                return
            
            retries += 1
        
        # Should not reach here, but handle it
        if last_exception:
            self.logger.error(f"Streaming failed after {self.config.max_retries} attempts")
            yield f"Error: {str(last_exception)}"
    
    async def validate_config(self) -> bool:
        """
        Validate the Ollama configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.config.base_url:
                self.logger.error("Ollama base URL is missing")
                return False
            
            if not self.config.model:
                self.logger.error("Ollama model is missing")
                return False
            
            # Use the connection verifier from base class
            return await self.connection_verifier.verify_connection()
                        
        except Exception as e:
            self.logger.error(f"Ollama configuration validation failed: {str(e)}")
            return False