"""
Base Ollama Provider for Pipeline Architecture

This module provides common functionality for Ollama providers.
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from abc import ABC, abstractmethod
from .llm_provider import LLMProvider


class OllamaBaseProvider(LLMProvider, ABC):
    """
    Base class for Ollama providers with shared configuration and options handling.
    """

    def __init__(self, config: Dict[str, Any], provider_key: str):
        """
        Initialize the base Ollama provider.

        Args:
            config: Configuration dictionary
            provider_key: Key to access provider-specific config (e.g., 'ollama', 'ollama_cloud')
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Get provider specific configuration
        provider_config = config.get('inference', {}).get(provider_key, {})
        if not provider_config:
            provider_config = config.get(provider_key, {})  # Backward compatibility

        self.provider_config = provider_config
        self.model = provider_config.get('model')

        # Common generation parameters
        self.temperature = provider_config.get('temperature', 0.1)
        self.top_p = provider_config.get('top_p', 0.8)
        self.top_k = provider_config.get('top_k')
        self.min_p = provider_config.get('min_p')
        self.typical_p = provider_config.get('typical_p')

        # Sampling controls
        self.repeat_penalty = provider_config.get('repeat_penalty')
        self.repeat_last_n = provider_config.get('repeat_last_n')
        self.presence_penalty = provider_config.get('presence_penalty')
        self.frequency_penalty = provider_config.get('frequency_penalty')

        # Mirostat sampling
        self.mirostat = provider_config.get('mirostat')
        self.mirostat_tau = provider_config.get('mirostat_tau')
        self.mirostat_eta = provider_config.get('mirostat_eta')

        # Context and output control
        self.num_ctx = provider_config.get('num_ctx')
        self.num_keep = provider_config.get('num_keep')
        self.penalize_newline = provider_config.get('penalize_newline')
        self.num_predict = provider_config.get('num_predict', 1024)

        # Stop sequences
        self.stop = provider_config.get('stop', [])

        # Seed
        self.seed = provider_config.get('seed')

        # Stream setting
        self.stream = provider_config.get('stream', True)

    def get_generation_options(self) -> Dict[str, Any]:
        """
        Get generation options dictionary with None values filtered out.

        Returns:
            Dictionary of generation options
        """
        options = {
            "temperature": self.temperature,
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
            "num_predict": self.num_predict,
        }

        # Add seed if specified
        if self.seed is not None:
            options["seed"] = self.seed

        # Filter out None values
        return {k: v for k, v in options.items() if v is not None}

    def prepare_messages(self, prompt: str, messages: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        """
        Prepare messages for chat format.

        Args:
            prompt: The input prompt
            messages: Optional pre-formatted messages

        Returns:
            List of message dictionaries
        """
        if messages is None:
            return [{"role": "user", "content": prompt}]
        return messages

    def parse_streaming_chunk(self, chunk: str, chat_format: bool = False) -> Optional[str]:
        """
        Parse a streaming chunk and extract the content.

        Args:
            chunk: Raw chunk from streaming response
            chat_format: Whether using chat format or generate format

        Returns:
            Extracted content or None if parsing fails
        """
        chunk = chunk.strip()
        if not chunk:
            return None

        try:
            data = json.loads(chunk)

            if chat_format:
                # Chat format response
                if "message" in data:
                    return data["message"].get("content", "")
            else:
                # Generate format response
                if "response" in data:
                    return data["response"]

            return None

        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON: {chunk}")
            return None

    @abstractmethod
    async def initialize(self, **kwargs) -> None:
        """Initialize the provider. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def validate_config(self) -> bool:
        """Validate configuration. Must be implemented by subclasses."""
        pass