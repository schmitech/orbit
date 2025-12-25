"""
OpenRouter inference service implementation using the native OpenRouter SDK.

This implementation uses the official OpenRouter Python SDK for improved
type safety, auto-generated model support, and native async capabilities.

SDK Documentation: https://openrouter.ai/docs/sdks/python/overview
"""

import logging
from typing import Dict, Any, AsyncGenerator, Optional

from openrouter import OpenRouter

from ...services import InferenceService


logger = logging.getLogger(__name__)


class OpenRouterInferenceService(InferenceService):
    """
    OpenRouter inference service using the native OpenRouter SDK.

    OpenRouter is a unified gateway to 300+ LLM providers with a single API.
    This implementation uses the official SDK for better type safety and
    automatic updates when new models are available.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the OpenRouter inference service."""
        # Initialize InferenceService (which extends ProviderAIService)
        super().__init__(config, "openrouter")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)

        # Resolve API key
        self.api_key = self._resolve_api_key("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide in configuration."
            )

        # Get model from config
        self.model = self._get_model()
        if not self.model:
            raise ValueError("OpenRouter model must be specified in configuration.")

        # Client will be initialized in initialize()
        self.client: Optional[OpenRouter] = None

        logger.info(f"Configured OpenRouter service with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the OpenRouter service."""
        try:
            if self.initialized:
                return True

            # Create OpenRouter client
            self.client = OpenRouter(api_key=self.api_key)

            self.initialized = True
            logger.info(f"Initialized OpenRouter inference service with model {self.model}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """Verify connection to OpenRouter."""
        try:
            if not self.client:
                logger.error("OpenRouter client is not initialized.")
                return False

            # Make a minimal test request
            response = await self.client.chat.send_async(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                temperature=0
            )

            if response and response.choices:
                logger.debug("OpenRouter connection verified successfully")
                return True

            return False

        except Exception as e:
            logger.error(f"OpenRouter connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the OpenRouter service and release resources."""
        if self.client:
            # OpenRouter client cleanup if needed
            self.client = None

        self.initialized = False
        logger.debug("Closed OpenRouter service")

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using OpenRouter."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            response = await self.client.chat.send_async(
                model=self.model,
                messages=messages,
                temperature=kwargs.pop('temperature', self.temperature),
                max_tokens=kwargs.pop('max_tokens', self.max_tokens),
                top_p=kwargs.pop('top_p', self.top_p),
                **kwargs
            )

            content = response.choices[0].message.content
            if content:
                # Filter out specific model artifacts
                content = content.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
            
            return content

        except Exception as e:
            self._handle_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using OpenRouter."""
        if not self.initialized:
            await self.initialize()

        try:
            messages = kwargs.pop('messages', None)
            if messages is None:
                messages = [{"role": "user", "content": prompt}]

            stream = await self.client.chat.send_async(
                model=self.model,
                messages=messages,
                temperature=kwargs.pop('temperature', self.temperature),
                max_tokens=kwargs.pop('max_tokens', self.max_tokens),
                top_p=kwargs.pop('top_p', self.top_p),
                stream=True,
                **kwargs
            )

            async for event in stream:
                if event.choices and event.choices[0].delta.content:
                    yield event.choices[0].delta.content

        except Exception as e:
            self._handle_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Handle OpenRouter API errors with appropriate logging."""
        logger.error(f"OpenRouter error during {operation}: {str(error)}")
