"""
Google Cloud-specific base class for Google AI services (Vertex AI & Gemini).

This module provides a unified base class for Google Cloud-based services,
consolidating common functionality like credential management and client initialization.
"""

from typing import Any, Optional
import logging
import threading

from ..base import ProviderAIService, ServiceType, verify_connection_via
from ..connection import RetryHandler
from ..errors import ErrorCategory, log_and_raise_sanitized



logger = logging.getLogger(__name__)
class GoogleBaseService(ProviderAIService):
    """
    Base class for all Google Cloud AI services (Vertex AI, Gemini).

    This class consolidates:
    - Google Cloud project and location configuration
    - Credential management
    - Common configuration patterns
    - Connection verification
    - Common Google error handling patterns
    """

    DEFAULT_LOCATION = "us-central1"

    # Shared across every Gemini-backed service instance/type (inference,
    # embedding, OCR, vision, image, video, audio) in this process, keyed by
    # resolved API key, so enabling several Gemini capabilities at once
    # doesn't open a separate genai.Client()/connection pool per capability.
    # Reference-counted so the client is actually closed and evicted once the
    # last instance using it is closed, instead of leaking for the life of
    # the process. `_genai_client_lock` is a threading.Lock (not asyncio.Lock)
    # because `_get_client` is sync and may run concurrently from
    # asyncio.to_thread worker threads, not just asyncio tasks on one thread.
    _shared_genai_clients: dict[str, Any] = {}
    _shared_genai_client_refcounts: dict[str, int] = {}
    _genai_client_lock = threading.Lock()

    def __init__(self, config: dict[str, Any], service_type: ServiceType, provider_name: str):
        """
        Initialize the Google base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name ("vertexai" or "gemini")
        """
        super().__init__(config, service_type, provider_name)
        self._genai_client = None
        self._genai_client_cache_key: Optional[str] = None
        self._genai_client_closed = False
        self._setup_google_config()

    def _setup_google_config(self) -> None:
        """
        Set up Google Cloud-specific configuration.

        This method:
        1. Gets the Google Cloud project ID
        2. Gets the location/region
        3. Initializes credentials if needed
        4. Gets model configuration
        """
        google_config = self._extract_provider_config()

        # Get project ID (required for Vertex AI)
        self.project_id = google_config.get("project_id") or self._resolve_api_key("GOOGLE_CLOUD_PROJECT", "project_id")

        # Get location/region
        self.location = google_config.get("location", self.DEFAULT_LOCATION)

        # Get model
        self.model = self._get_model()

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        logger.debug(
            f"Configured {self.provider_name.title()} service with model: {self.model}"
        )

    async def initialize(self) -> bool:
        """
        Initialize the Google Cloud service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.initialized = True
            logger.debug(
                f"Initialized {self.provider_name.title()} {self.service_type.value} service "
                f"with model {self.model}"
            )
            return True
        except Exception as e:  # noqa: BLE001 - provider boundary fallback
            logger.error(f"Failed to initialize {self.provider_name.title()} service: {e!s}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Google Cloud connection.

        Returns:
            True if the connection is working, False otherwise
        """
        async def _probe() -> bool:
            # Basic validation
            if self.provider_name == "vertexai" and not self.project_id:
                logger.error("Vertex AI requires project_id")
                return False

            logger.debug(f"{self.provider_name.title()} connection verified")
            return True

        return await verify_connection_via(logger, _probe, provider=self.provider_name.title())

    async def close(self) -> None:
        """Close the Google Cloud service and release resources."""
        self._release_client()
        self.initialized = False
        logger.debug(f"Closed {self.provider_name.title()} service")

    def _get_max_tokens(self, default: int = 1024) -> int:
        """Get max_tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_temperature(self, default: float = 0.7) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_top_k(self, default: int = 40) -> int:
        """Get top_k configuration (Google-specific)."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_k', default)

    def _get_client(self):
        """
        Get or create the shared google-genai Client for this service's
        resolved API key.

        Reused across every Gemini-backed service type that resolves to the
        same API key, instead of each one holding its own client/connection
        pool. Reference-counted: each instance that successfully gets a
        client here must call `_release_client` (done via `close()`) so the
        shared client is closed once nothing is using it any more.

        The initial "already have one" check and all instance-state mutation
        happen under the same lock `_release_client` uses, so a concurrent
        `_get_client()`/`close()` pair on the same instance can't interleave:
        one fully completes (and is correctly counted) before the other
        starts. If `close()` has already run for this instance (e.g. a
        worker reaches this call after shutdown released the instance),
        building — and leaking — a fresh, never-released reference is
        refused outright instead.
        """
        with GoogleBaseService._genai_client_lock:
            if self._genai_client_closed:
                raise RuntimeError(
                    f"{self.provider_name.title()} service was already closed; "
                    "cannot create a new genai.Client for it."
                )

            if self._genai_client is not None:
                return self._genai_client

            import os

            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key

            cache_key = api_key or ""
            client = GoogleBaseService._shared_genai_clients.get(cache_key)
            if client is None:
                try:
                    from google import genai
                except ImportError:
                    raise ImportError(
                        "google-genai package is required for Gemini services. "
                        "Install it with: pip install google-genai"
                    )
                client = genai.Client()
                GoogleBaseService._shared_genai_clients[cache_key] = client
                GoogleBaseService._shared_genai_client_refcounts[cache_key] = 0

            GoogleBaseService._shared_genai_client_refcounts[cache_key] += 1
            self._genai_client_cache_key = cache_key
            self._genai_client = client
            return self._genai_client

    def _release_client(self) -> None:
        """
        Release this instance's reference to its shared genai.Client.

        Closes and evicts the client from the shared cache once no other
        instance holds a reference to it. Safe to call even if this instance
        never built a client.

        Reads and clears this instance's state under the same lock
        `_get_client` uses (see its docstring) rather than before taking the
        lock, so a `_get_client()` call racing a `close()` on the same
        instance can't grab a reference that this release then silently
        forgets to account for. Also marks the instance closed under that
        same lock, so a `_get_client()` call that arrives after this one has
        released its reference is refused instead of silently building (and
        leaking) a fresh one that nothing will ever release.
        """
        client_to_close = None
        with GoogleBaseService._genai_client_lock:
            self._genai_client_closed = True
            cache_key = self._genai_client_cache_key
            self._genai_client = None
            self._genai_client_cache_key = None
            if cache_key is None:
                return

            remaining = GoogleBaseService._shared_genai_client_refcounts.get(cache_key, 1) - 1
            if remaining > 0:
                GoogleBaseService._shared_genai_client_refcounts[cache_key] = remaining
            else:
                GoogleBaseService._shared_genai_client_refcounts.pop(cache_key, None)
                client_to_close = GoogleBaseService._shared_genai_clients.pop(cache_key, None)

        if client_to_close is not None:
            try:
                client_to_close.close()
            except Exception as e:  # noqa: BLE001 - best-effort cleanup
                logger.debug(f"Error closing shared genai.Client: {e!s}")

    def _handle_google_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Google Cloud-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error).lower()
        message = None

        if "authentication" in error_str or "credential" in error_str:
            category = ErrorCategory.AUTH
            message = "{provider} authentication failed during {operation}: Invalid credentials"
        elif "quota" in error_str:
            category = ErrorCategory.QUOTA
            message = "{provider} quota exceeded during {operation}"
        elif "permission" in error_str:
            category = ErrorCategory.PERMISSION
        else:
            category = ErrorCategory.API
            message = "{provider} error during {operation}: {error}"

        log_and_raise_sanitized(
            logger, error, provider=self.provider_name, operation=operation,
            category=category, message=message,
        )
