"""
Ollama inference service implementation using unified architecture.

This is a migrated version of the Ollama inference provider that uses
the new unified AI services architecture and integrates with existing
ollama_utils for maximum compatibility.
"""

import logging
from typing import Dict, Any, AsyncGenerator
import json

from ..base import ServiceType
from ..providers import OllamaBaseService
from ..services import InferenceService

logger = logging.getLogger(__name__)


class OllamaInferenceService(InferenceService, OllamaBaseService):
    """
    Ollama inference service using unified architecture.

    This implementation leverages:
    1. Ollama utilities integration from OllamaBaseService
    2. Model warm-up and retry logic inherited
    3. Configuration parsing from base classes
    4. Connection verification automatic

    Simplified with automatic handling of Ollama-specific functionality.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama inference service.

        Args:
            config: Configuration dictionary
        """
        # Initialize via InferenceService which will cooperate with OllamaBaseService
        InferenceService.__init__(self, config, "ollama")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.top_p = self._get_top_p(default=0.9)

        # Ollama doesn't have max_tokens, uses num_predict instead
        provider_config = self._extract_provider_config()
        self.num_predict = provider_config.get('num_predict', -1)  # -1 means no limit
        self.think = provider_config.get('think', False)  # Enable/disable think mode

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Ollama.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for chat format)

        Returns:
            The generated response text
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama inference service")

        async def _generate():
            session = await self.session_manager.get_session()

            # Check if we have messages format (chat)
            messages = kwargs.pop('messages', None)

            if messages:
                # Use chat endpoint for messages
                url = f"{self.base_url}/api/chat"
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                    }
                }
            else:
                # Use generate endpoint for simple prompts
                url = f"{self.base_url}/api/generate"
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                        "num_predict": kwargs.pop('num_predict', self.num_predict),
                    }
                }

            # Add any other kwargs to options
            payload["options"].update(kwargs)

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama error: {error_text}")

                data = await response.json()

                # Get response based on endpoint used
                if messages:
                    return data.get('message', {}).get('content', '')
                else:
                    return data.get('response', '')

        # Use Ollama's retry handler
        return await self.execute_with_retry(_generate)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for chat format)

        Yields:
            Response chunks as they are generated
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama inference service")

        try:
            session = await self.session_manager.get_session()

            # Check if we have messages format (chat)
            messages = kwargs.pop('messages', None)

            if messages:
                # Use chat endpoint for messages
                url = f"{self.base_url}/api/chat"
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                    }
                }
            else:
                # Use generate endpoint for simple prompts
                url = f"{self.base_url}/api/generate"
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                        "num_predict": kwargs.pop('num_predict', self.num_predict),
                    }
                }

            # Add any other kwargs to options
            payload["options"].update(kwargs)

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield f"Error: {error_text}"
                    return

                # Stream the response
                async for line in response.content:
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))

                            # Get content based on endpoint used
                            if messages:
                                content = chunk.get('message', {}).get('content', '')
                            else:
                                content = chunk.get('response', '')

                            if content:
                                yield content

                            # Check if done
                            if chunk.get('done', False):
                                break

                        except json.JSONDecodeError:
                            continue  # Skip invalid JSON lines

        except Exception as e:
            logger.error(f"Error in streaming generation: {str(e)}")
            yield f"Error: {str(e)}"
