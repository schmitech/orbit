"""
Ollama Provider for Pipeline Architecture

This module provides a clean Ollama implementation for the pipeline architecture.
"""

import json
import logging
import time
from typing import Dict, Any, AsyncGenerator, Optional
import aiohttp
from .ollama_base_provider import OllamaBaseProvider
from utils.ollama_utils import OllamaBaseService, OllamaConfig


class OllamaProvider(OllamaBaseProvider, OllamaBaseService):
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
        # Initialize base provider
        OllamaBaseProvider.__init__(self, config, 'ollama')

        # Initialize base service
        OllamaBaseService.__init__(self, config, 'inference')

        # Additional local Ollama settings (hardware-specific)
        ollama_config = self.provider_config
        self.num_batch = ollama_config.get('num_batch', 2)
        self.num_gpu = ollama_config.get('num_gpu', 0)
        self.main_gpu = ollama_config.get('main_gpu', 0)
        self.low_vram = ollama_config.get('low_vram', False)
        self.use_mmap = ollama_config.get('use_mmap', True)
        self.use_mlock = ollama_config.get('use_mlock', False)
        self.vocab_only = ollama_config.get('vocab_only', False)
        self.numa = ollama_config.get('numa', False)

    def get_hardware_options(self) -> Dict[str, Any]:
        """
        Get hardware-specific options for local Ollama.

        Returns:
            Dictionary of hardware options
        """
        return {
            "num_batch": self.num_batch,
            "num_gpu": self.num_gpu,
            "main_gpu": self.main_gpu,
            "low_vram": self.low_vram,
            "use_mmap": self.use_mmap,
            "use_mlock": self.use_mlock,
            "vocab_only": self.vocab_only,
            "numa": self.numa,
        }

    def get_all_options(self) -> Dict[str, Any]:
        """
        Get all options including generation and hardware settings.

        Returns:
            Combined dictionary of all options
        """
        options = self.get_generation_options()
        options.update(self.get_hardware_options())
        return options

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
                # Use chat endpoint
                messages = self.prepare_messages(prompt, messages)
                options = self.get_all_options()

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
                # Use generate endpoint
                options = self.get_all_options()

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
                    # Use chat endpoint
                    messages = self.prepare_messages(prompt, messages)
                    options = self.get_all_options()

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
                            chunk = line.decode('utf-8')
                            content = self.parse_streaming_chunk(chunk, chat_format=True)
                            if content:
                                yield content

                            # Check for completion
                            if chunk.strip():
                                try:
                                    data = json.loads(chunk.strip())
                                    if data.get("done", False):
                                        break
                                except:
                                    pass
                else:
                    # Use generate endpoint
                    options = self.get_all_options()

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
                            chunk = line.decode('utf-8')
                            content = self.parse_streaming_chunk(chunk, chat_format=False)
                            if content:
                                yield content

                            # Check for completion
                            if chunk.strip():
                                try:
                                    data = json.loads(chunk.strip())
                                    if data.get("done", False):
                                        break
                                except:
                                    pass

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