"""
Ollama Cloud inference service implementation for the unified architecture.

This service provides a dedicated implementation for Ollama Cloud that mirrors
the behaviour of the legacy pipeline provider while fitting into the unified
AI services framework.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from ollama import AsyncClient

from ...services import InferenceService

logger = logging.getLogger(__name__)


class OllamaCloudInferenceService(InferenceService):
    """Inference service for the managed Ollama Cloud offering."""

    _OPTION_KEYS = (
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "presence_penalty",
        "frequency_penalty",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
        "num_ctx",
        "num_keep",
        "penalize_newline",
        "num_predict",
        "seed",
    )

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config, "ollama_cloud")

        provider_config = self._extract_provider_config()

        # InferenceService doesn't persist top_p, so store it locally
        self.top_p = provider_config.get("top_p", self._get_top_p())

        self.api_key: Optional[str] = provider_config.get("api_key")
        self.base_url: str = provider_config.get("base_url", "https://ollama.com")
        self.model = self._get_model()

        # Override inherited defaults with provider configuration
        self.temperature = provider_config.get("temperature", self.temperature)

        self._default_options: Dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

        for key in self._OPTION_KEYS:
            value = provider_config.get(key)
            if value is not None:
                self._default_options[key] = value

        # num_predict controls maximum output length for Ollama
        if "num_predict" not in self._default_options and self.max_tokens:
            self._default_options["num_predict"] = self.max_tokens

        self._stop_sequences: List[str] = provider_config.get("stop", [])

        # Think mode (shows reasoning in <think> tags) - matches local Ollama behavior
        self.think: bool = provider_config.get("think", False)

        self.client: Optional[AsyncClient] = None

    async def initialize(self) -> bool:
        """Initialise the Ollama Cloud client and verify connectivity."""
        if self.initialized:
            return True

        if not self.api_key:
            logger.error("Ollama Cloud API key is not configured")
            return False

        try:
            self.client = AsyncClient(
                host=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )

            if await self.verify_connection():
                self.initialized = True
                logger.info(
                    "Initialized Ollama Cloud inference service with model %s",
                    self.model,
                )
                return True
            else:
                logger.warning("Ollama Cloud connection verification failed")
                return False

        except Exception as exc:
            logger.error(f"Failed to initialize Ollama Cloud client: {exc}")
            self.client = None
            return False

    async def close(self) -> None:
        """Release the client. AsyncClient does not expose close()."""
        self.client = None
        self.initialized = False

    async def verify_connection(self) -> bool:
        """Verify that the Ollama Cloud credentials and model are valid."""
        try:
            if not self.api_key:
                logger.error("Ollama Cloud API key is not configured")
                return False
                
            # Use the existing client if available, otherwise create a temporary one
            if not self.client:
                temp_client = AsyncClient(
                    host=self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            else:
                temp_client = self.client

            # Try a simple model list request first (lighter than a chat request)
            try:
                models = await temp_client.list()
                if models and hasattr(models, 'models') and models.models:
                    logger.debug("Ollama Cloud connection verified successfully")
                    return True
            except Exception as list_exc:
                logger.debug(f"Model list failed, trying chat request: {list_exc}")
                
                # Fallback to a minimal chat request
                await temp_client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": "ping"}],
                    options={"num_predict": 1},
                )
                
            return True
        except Exception as exc:
            logger.error("Failed to verify Ollama Cloud connection: %s", exc)
            return False
        finally:
            if 'temp_client' in locals() and temp_client is not self.client:
                temp_client = None

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate a non-streaming response using Ollama Cloud."""
        if not self.initialized and not await self.initialize():
            raise ValueError("Failed to initialize Ollama Cloud inference service")

        assert self.client is not None  # for type checkers

        try:
            kwargs.pop("stream", None)
            messages = self._prepare_messages(prompt, kwargs.pop("messages", None))
            options = self._build_options(kwargs)
            stop = kwargs.pop("stop", None)
            if stop is None:
                stop = self._stop_sequences or None
            if stop:
                options["stop"] = stop

            # Extract think parameter (shows reasoning in <think> tags)
            think = kwargs.pop("think", self.think)

            response = await self.client.chat(
                model=self.model,
                messages=messages,
                options=options,
                think=think,
                **kwargs,
            )

            return self._extract_content(response)
        except Exception as exc:
            logger.error("Error generating response with Ollama Cloud: %s", exc)
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate a streaming response using Ollama Cloud."""
        if not self.initialized and not await self.initialize():
            raise ValueError("Failed to initialize Ollama Cloud inference service")

        assert self.client is not None

        try:
            kwargs.pop("stream", None)
            messages = self._prepare_messages(prompt, kwargs.pop("messages", None))
            options = self._build_options(kwargs)
            stop = kwargs.pop("stop", None)
            if stop is None:
                stop = self._stop_sequences or None
            if stop:
                options["stop"] = stop

            # Extract think parameter (shows reasoning in <think> tags)
            think = kwargs.pop("think", self.think)

            stream = await self.client.chat(
                model=self.model,
                messages=messages,
                options=options,
                stream=True,
                think=think,
                **kwargs,
            )

            async for chunk in stream:
                content = self._extract_content(chunk)
                if content:
                    yield content
        except Exception as exc:
            logger.error("Error generating streaming response with Ollama Cloud: %s", exc)
            yield f"Error: {exc}"

    def _build_options(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Merge default generation options with caller overrides."""
        options = dict(self._default_options)

        token_override = None
        for key in ("num_predict", "max_tokens", "max_completion_tokens", "max_output_tokens"):
            if key in overrides:
                value = overrides.pop(key)
                if value is not None:
                    token_override = value

        for key in self._OPTION_KEYS:
            if key in overrides:
                value = overrides.pop(key)
                if value is None:
                    options.pop(key, None)
                else:
                    options[key] = value

        if token_override is not None:
            options["num_predict"] = token_override

        # Ensure no None values are passed to the API
        return {k: v for k, v in options.items() if v is not None}

    @staticmethod
    def _prepare_messages(prompt: str, messages: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        if messages is None:
            return [{"role": "user", "content": prompt}]
        return messages

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Extract content from Ollama SDK response.

        The Ollama SDK returns ChatResponse Pydantic objects, not dicts.
        This method handles both object attribute access and dict-style access
        for compatibility with different SDK versions.

        Args:
            response: The response from ollama.chat() - either ChatResponse object or dict

        Returns:
            The message content as a string, or empty string if not found
        """
        # Try attribute access first (Pydantic model / ChatResponse object)
        if hasattr(response, 'message'):
            message = response.message
            if hasattr(message, 'content'):
                return message.content or ""
            # Fallback to dict-style access on message
            if isinstance(message, dict):
                return message.get('content', '')
            return ""

        # Fallback to dict-style access (legacy or raw response)
        if isinstance(response, dict):
            return response.get("message", {}).get("content", "")

        # If response has a model_dump method (Pydantic v2), use it
        if hasattr(response, 'model_dump'):
            data = response.model_dump()
            return data.get("message", {}).get("content", "")

        logger.warning(f"Unexpected response type from Ollama Cloud: {type(response)}")
        return ""
