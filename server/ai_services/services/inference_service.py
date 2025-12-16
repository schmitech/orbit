"""
Inference service interface and base implementations.

This module defines the common interface for all LLM inference services,
providing a unified API for text generation regardless of the underlying provider.
"""

from abc import abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional, List
import logging
import time
import uuid

from ..base import ProviderAIService, ServiceType



logger = logging.getLogger(__name__)

# OpenAI-compatible chat message payload used by helper utilities.
ChatMessage = Dict[str, Any]


class InferenceService(ProviderAIService):
    """
    Base class for all LLM inference services.

    This class defines the common interface that all inference service
    implementations must follow, regardless of provider (OpenAI, Anthropic,
    Ollama, etc.).

    Key Methods:
        - generate: Generate text response (non-streaming)
        - generate_stream: Generate streaming text response
        - validate_config: Validate configuration

    Configuration Support:
        - Configurable endpoints via config
        - Temperature, top_p, max_tokens
        - Streaming support
    """

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the inference service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'openai', 'anthropic')
        """
        super().__init__(config, ServiceType.INFERENCE, provider_name)
        self.temperature: float = self._get_temperature()
        self.max_tokens: int = self._get_max_tokens()
        self.stream_enabled: bool = self._get_stream_enabled()

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response for the given prompt.

        This method supports both simple prompt strings and structured
        conversation formats via the 'messages' kwarg.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters including:
                - messages: List[Dict] - Structured conversation format
                - temperature: float - Override default temperature
                - max_tokens: int - Override default max tokens
                - top_p: float - Nucleus sampling parameter
                - stop: List[str] - Stop sequences

        Returns:
            The generated response text

        Raises:
            ValueError: If the service is not initialized
            Exception: For provider-specific errors

        Example:
            >>> service = OpenAIInferenceService(config)
            >>> await service.initialize()
            >>> response = await service.generate("Hello, how are you?")
            >>> print(response)
            "I'm doing well, thank you!"
        """
        pass

    @abstractmethod
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response.

        This method yields response chunks as they are generated, enabling
        real-time streaming of text.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (same as generate())

        Yields:
            Response chunks as they are generated

        Raises:
            ValueError: If the service is not initialized
            Exception: For provider-specific errors

        Example:
            >>> service = OpenAIInferenceService(config)
            >>> await service.initialize()
            >>> async for chunk in service.generate_stream("Tell me a story"):
            ...     print(chunk, end='', flush=True)
        """
        pass

    async def validate_config(self) -> bool:
        """
        Validate provider configuration.

        This checks that the configuration is valid and the service
        can successfully connect to the provider.

        Returns:
            True if configuration is valid, False otherwise

        Example:
            >>> service = OpenAIInferenceService(config)
            >>> is_valid = await service.validate_config()
            >>> print(is_valid)
            True
        """
        try:
            # Basic validation
            if not self.model:
                logger.error("Model not configured")
                return False

            if not self.api_key and self.provider_name != "ollama":
                logger.error("API key not configured")
                return False

            # Verify connection
            return await self.verify_connection()

        except Exception as e:
            logger.error(f"Configuration validation failed: {str(e)}")
            return False

    def _get_temperature(self, default: float = 0.7) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default temperature if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 2000) -> int:
        """
        Get max_tokens configuration.

        Args:
            default: Default max tokens if not configured

        Returns:
            Maximum number of tokens
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default top_p if not configured

        Returns:
            Top-p value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_stream_enabled(self, default: bool = True) -> bool:
        """
        Get stream configuration.

        Args:
            default: Default stream setting if not configured

        Returns:
            Whether streaming is enabled
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('stream', default)

    async def generate_with_fallback(
        self,
        prompt: str,
        fallback_response: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate with optional fallback on error.

        Args:
            prompt: The input prompt
            fallback_response: Optional fallback response on error
            **kwargs: Additional generation parameters

        Returns:
            Generated response or fallback

        Example:
            >>> response = await service.generate_with_fallback(
            ...     "Hello",
            ...     fallback_response="I apologize, but I'm unable to respond."
            ... )
        """
        try:
            return await self.generate(prompt, **kwargs)
        except Exception as e:
            logger.error(f"Generation failed, using fallback: {str(e)}")
            if fallback_response is not None:
                return fallback_response
            raise

    async def generate_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
        **kwargs
    ) -> str:
        """
        Generate with automatic retry on failure.

        Args:
            prompt: The input prompt
            max_retries: Maximum number of retry attempts
            **kwargs: Additional generation parameters

        Returns:
            Generated response

        Example:
            >>> response = await service.generate_with_retry(
            ...     "Hello",
            ...     max_retries=3
            ... )
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.generate(prompt, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Generation attempt {attempt + 1} failed, retrying: {str(e)}"
                    )
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        logger.error(f"Generation failed after {max_retries} attempts")
        raise last_error


class InferenceResult:
    """
    Structured result for inference operations.

    This class provides a standardized way to return inference results
    with metadata.
    """

    def __init__(
        self,
        response: str,
        model: str,
        provider: str,
        tokens_used: Optional[int] = None,
        finish_reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize inference result.

        Args:
            response: Generated text response
            model: Model used for generation
            provider: Provider name
            tokens_used: Number of tokens consumed
            finish_reason: Reason generation stopped
            metadata: Optional metadata
        """
        self.response = response
        self.model = model
        self.provider = provider
        self.tokens_used = tokens_used
        self.finish_reason = finish_reason
        self.metadata = metadata or {}

    def __str__(self) -> str:
        """Return the response text."""
        return self.response

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'response': self.response,
            'model': self.model,
            'provider': self.provider,
            'tokens_used': self.tokens_used,
            'finish_reason': self.finish_reason,
            'metadata': self.metadata
        }


class OpenAIResponseFormatter:
    """
    Helper to format ORBIT responses into OpenAI-compatible payloads.

    This utility consolidates shared logic so routes can expose responses that
    the official OpenAI Python SDK (and any OpenAI-compatible client) accepts
    without needing provider-specific transformations per endpoint.
    """

    def __init__(self, model: Optional[str], provider: Optional[str]):
        self.model = model or "orbit"
        self.provider = provider or "orbit"
        self.completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        self.created = int(time.time())

    def build_usage(
        self,
        usage: Optional[Dict[str, int]],
        metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Return usage payload with sensible defaults."""
        if usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        metadata = metadata or {}
        prompt_tokens = metadata.get("prompt_tokens", 0)
        completion_tokens = metadata.get("completion_tokens", 0)
        total_tokens = metadata.get("total_tokens", prompt_tokens + completion_tokens)

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def build_orbit_extension(
        self,
        *,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        audio: Optional[str] = None,
        audio_format: Optional[str] = None,
        threading: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Bundle ORBIT-specific metadata into a single extension block so clients
        can opt-in without polluting the OpenAI response schema.
        """
        extension: Dict[str, Any] = {}
        if sources:
            extension["sources"] = sources
        if metadata:
            extension["metadata"] = metadata
        if audio:
            extension["audio"] = audio
        if audio_format:
            extension["audio_format"] = audio_format
        if threading:
            extension["threading"] = threading
        if extra:
            extension.update(extra)

        return extension or None

    def build_completion_response(
        self,
        *,
        content: str,
        finish_reason: str = "stop",
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        audio: Optional[str] = None,
        audio_format: Optional[str] = None,
        threading: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a complete OpenAI-style chat completion response."""
        response = {
            "id": self.completion_id,
            "object": "chat.completion",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": finish_reason,
                    "logprobs": None
                }
            ],
            "usage": self.build_usage(usage, metadata),
            "system_fingerprint": self.provider
        }

        orbit_extension = self.build_orbit_extension(
            sources=sources,
            metadata=metadata,
            audio=audio,
            audio_format=audio_format,
            threading=threading
        )
        if orbit_extension:
            response["orbit"] = orbit_extension

        return response

    def build_stream_chunk(
        self,
        *,
        content: Optional[str] = None,
        finish_reason: Optional[str] = None,
        usage: Optional[Dict[str, int]] = None,
        role: Optional[str] = None,
        orbit_extension: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build a single streaming chunk compatible with OpenAI's SSE format.
        """
        delta: Dict[str, Any] = {}
        if role:
            delta["role"] = role
        if content is not None:
            delta["content"] = content

        chunk = {
            "id": self.completion_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                    "logprobs": None
                }
            ],
            "system_fingerprint": self.provider
        }

        if usage:
            chunk["usage"] = usage
        if orbit_extension:
            chunk["orbit"] = orbit_extension

        return chunk


# Import for async operations
import asyncio


# Helper function for service creation
def create_inference_service(
    provider: str,
    config: Dict[str, Any]
) -> InferenceService:
    """
    Factory function to create an inference service.

    Args:
        provider: Provider name (e.g., 'openai', 'anthropic')
        config: Configuration dictionary

    Returns:
        Inference service instance

    Example:
        >>> service = create_inference_service('openai', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.INFERENCE,
        provider,
        config
    )
