"""
OpenAI inference service implementation using unified architecture.

This is a migrated version of the OpenAI inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/openai_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ..base import ServiceType
from ..providers import OpenAIBaseService
from ..services import InferenceService


class OpenAIInferenceService(InferenceService, OpenAIBaseService):
    """
    OpenAI inference service using unified architecture.

    This implementation is dramatically simpler because:
    1. API key management handled by OpenAIBaseService
    2. AsyncOpenAI client initialization handled by OpenAIBaseService
    3. Configuration parsing handled by base classes
    4. Connection verification handled by base classes
    5. Error handling via _handle_openai_error()

    Old implementation: ~158 lines
    New implementation: ~70 lines focused only on inference logic
    Reduction: ~56%
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI inference service.

        Args:
            config: Configuration dictionary

        Note: All setup (API key, client, etc.) handled by base classes!
        """
        # Initialize via OpenAIBaseService first, which will call ProviderAIService
        # This ensures the model is properly extracted from config
        OpenAIBaseService.__init__(self, config, ServiceType.INFERENCE, "openai")

        # Get inference-specific configuration (these will override the defaults from InferenceService)
        self.temperature = self._get_temperature(default=0.1)
        self.max_tokens = self._get_max_tokens(default=2000)
        self.top_p = self._get_top_p(default=1.0)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                token_param: token_value,
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None:
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if self._supports_top_p():
                params["top_p"] = top_p_value

            params.update(kwargs)  # Any other parameters

            response = await self.client.chat.completions.create(**params)

            return response.choices[0].message.content

        except Exception as e:
            self._handle_openai_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages = kwargs.pop('messages', None)

            if messages is None:
                # Traditional format - convert to messages
                messages = [{"role": "user", "content": prompt}]

            # Build parameters using configured values
            # Handle max_tokens-style variants for different models/endpoints
            token_param = self._get_token_parameter_name()
            token_value = self._resolve_token_value(token_param, kwargs)

            params = {
                "model": self.model,
                "messages": messages,
                token_param: token_value,
                "stream": True,
            }

            temperature = kwargs.pop('temperature', self.temperature)
            if temperature is not None:
                params["temperature"] = temperature

            top_p_value = kwargs.pop('top_p', self.top_p)
            if self._supports_top_p():
                params["top_p"] = top_p_value

            params.update(kwargs)  # Any other parameters

            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_openai_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _get_token_parameter_name(self) -> str:
        """Return the correct token-count parameter name for the active model."""
        provider_config = self._extract_provider_config()

        # Allow explicit configuration override
        configured_name = provider_config.get("token_parameter_name") or provider_config.get("token_parameter")
        if isinstance(configured_name, str):
            configured_name = configured_name.strip()
            if configured_name:
                return configured_name

        model_name = (self.model or "").lower()

        # Newer OpenAI chat models expect max_completion_tokens when using the chat.completions API
        modern_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        if model_name.startswith(modern_prefixes):
            return "max_completion_tokens"

        # Default to the legacy chat.completions parameter name
        return "max_tokens"

    def _resolve_token_value(self, token_param: str, kwargs: Dict[str, Any]) -> int:
        """Determine the token limit value while respecting caller overrides."""
        # Pop all known token parameter variants so they don't leak into kwargs
        overrides = {
            "max_tokens": kwargs.pop("max_tokens", None),
            "max_completion_tokens": kwargs.pop("max_completion_tokens", None),
            "max_output_tokens": kwargs.pop("max_output_tokens", None),
        }

        # Caller provided the exact parameter we plan to use
        param_override = overrides.get(token_param)
        if param_override is not None:
            return param_override

        # Fall back to whichever override was provided, regardless of naming
        for value in overrides.values():
            if value is not None:
                return value

        # No override found; use configured default
        return self.max_tokens

    def _supports_top_p(self) -> bool:
        """Return whether the current model supports the top_p parameter."""
        model_name = (self.model or "").lower()

        # Current OpenAI docs list top_p as unsupported for newer models (4.1/4o/5/o-series)
        unsupported_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        return not model_name.startswith(unsupported_prefixes)
