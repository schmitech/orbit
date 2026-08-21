"""
OpenRouter inference service implementation using the native OpenRouter SDK.

This implementation uses the official OpenRouter Python SDK for improved
type safety, auto-generated model support, and native async capabilities.

SDK Documentation: https://openrouter.ai/docs/sdks/python/overview
"""

import logging
from typing import Dict, Any, AsyncGenerator, Optional

from openrouter import OpenRouter

from ...errors import raise_sanitized
from ...providers.usage_reporting import UsageReportingMixin
from ...services import InferenceService


logger = logging.getLogger(__name__)


class OpenRouterInferenceService(UsageReportingMixin, InferenceService):
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

        logger.debug(f"Configured OpenRouter service with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the OpenRouter service."""
        try:
            if self.initialized:
                return True

            # Create OpenRouter client
            self.client = OpenRouter(api_key=self.api_key)

            self.initialized = True
            logger.debug(f"Initialized OpenRouter inference service with model {self.model}")
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

    def _prepare_params(self, prompt: str, kwargs: dict) -> dict:
        """Extract and clean parameters for OpenRouter API request."""
        # Pop pipeline internal parameters that shouldn't leak to OpenRouter API
        kwargs.pop('cache_prefix_len', None)

        web_search = kwargs.pop('web_search', False)
        if web_search and 'plugins' not in kwargs:
            kwargs['plugins'] = [{'id': 'web'}]

        messages = kwargs.pop('messages', None)
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        else:
            clean_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if content is None:
                        content = ""
                    elif not isinstance(content, (str, list, dict)):
                        content = str(content)
                    clean_messages.append({"role": role, "content": content})
            messages = clean_messages

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.pop('temperature', self.temperature),
            "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
            "top_p": kwargs.pop('top_p', self.top_p),
        }
        params.update(kwargs)
        return params

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using OpenRouter."""
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            params = self._prepare_params(prompt, kwargs)
            response = await self.client.chat.send_async(**params)

            usage = getattr(response, "usage", None)
            if usage is not None:
                self._report_usage(
                    usage_sink,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
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
        usage_sink = self._take_usage_sink(kwargs)
        if not self.initialized:
            await self.initialize()

        try:
            params = self._prepare_params(prompt, kwargs)
            params['stream'] = True
            stream = await self.client.chat.send_async(**params)

            async for event in stream:
                # OpenRouter delivers mid-stream failures as a normal SSE data
                # chunk carrying an `error` field (the HTTP response already
                # started with 200), not as a raised exception - so it must be
                # checked explicitly on every chunk.
                error = getattr(event, "error", None)
                if error is not None:
                    raise RuntimeError(f"OpenRouter stream error {error.code}: {error.message}")

                if event.choices and event.choices[0].delta.content:
                    yield event.choices[0].delta.content

                usage = getattr(event, "usage", None)
                if usage is not None:
                    self._report_usage(
                        usage_sink,
                        getattr(usage, "prompt_tokens", None),
                        getattr(usage, "completion_tokens", None),
                    )

        except Exception as e:
            self._handle_error(e, "streaming generation")
            yield f"Error: {str(e)}"

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Handle OpenRouter API errors with appropriate logging."""
        details = ""
        body = getattr(error, "body", None)
        if not body and hasattr(error, "raw_response"):
            raw_resp = getattr(error, "raw_response")
            try:
                body = getattr(raw_resp, "text", None)
            except Exception:
                body = None
        if body:
            details = f" - Raw response: {body}"
        logger.error(f"OpenRouter error during {operation}: {str(error)}{details}")
        raise_sanitized(error, provider="openrouter", operation=operation)
