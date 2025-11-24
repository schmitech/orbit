"""
Connection management utilities for AI services.

This module provides reusable connection management, retry logic,
and timeout handling for all AI services.
"""

import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, TypeVar, Awaitable
from functools import wraps
import time

T = TypeVar('T')

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages HTTP connections for AI services with automatic session management.

    This class handles the creation, reuse, and cleanup of HTTP sessions,
    along with proper header management and timeout configuration.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout_ms: int = 30000,
        headers: Optional[Dict[str, str]] = None
    ):
        """
        Initialize the connection manager.

        Args:
            base_url: Base URL for API requests
            api_key: API key for authentication (if required)
            timeout_ms: Timeout in milliseconds (default: 30000)
            headers: Additional headers to include in requests
        """
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self.custom_headers = headers or {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(f"{__name__}.ConnectionManager")

    async def get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an HTTP session.

        Returns:
            Active aiohttp ClientSession
        """
        if self.session is None or self.session.closed:
            headers = self.custom_headers.copy()

            # Add authorization header if API key is provided
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Add common headers
            headers.setdefault("Content-Type", "application/json")

            timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000)

            self.session = aiohttp.ClientSession(
                base_url=self.base_url,
                headers=headers,
                timeout=timeout
            )

            logger.debug(f"Created new HTTP session for {self.base_url}")

        return self.session

    async def close(self) -> None:
        """Close the HTTP session and release resources."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            logger.debug("Closed HTTP session")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class RetryHandler:
    """
    Handles retry logic with exponential backoff for AI service operations.

    This class implements a configurable retry mechanism that can be used
    by any AI service to handle transient failures.
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_wait_ms: int = 1000,
        max_wait_ms: int = 30000,
        exponential_base: float = 2.0,
        enabled: bool = True
    ):
        """
        Initialize the retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            initial_wait_ms: Initial wait time in milliseconds
            max_wait_ms: Maximum wait time in milliseconds
            exponential_base: Base for exponential backoff calculation
            enabled: Whether retry logic is enabled
        """
        self.max_retries = max_retries
        self.initial_wait_ms = initial_wait_ms
        self.max_wait_ms = max_wait_ms
        self.exponential_base = exponential_base
        self.enabled = enabled
        self.logger = logging.getLogger(f"{__name__}.RetryHandler")

    def _calculate_wait_time(self, attempt: int) -> float:
        """
        Calculate wait time for a given attempt using exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Wait time in seconds
        """
        wait_ms = min(
            self.initial_wait_ms * (self.exponential_base ** attempt),
            self.max_wait_ms
        )
        return wait_ms / 1000

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        error_message: str = "Operation failed"
    ) -> T:
        """
        Execute an operation with retry logic.

        Args:
            operation: Async function to execute
            error_message: Error message to log on failure

        Returns:
            Result of the operation

        Raises:
            Exception: The last exception encountered if all retries fail
        """
        if not self.enabled:
            return await operation()

        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await operation()

            except Exception as e:
                last_exception = e

                # Don't retry on the last attempt
                if attempt >= self.max_retries:
                    logger.error(
                        f"{error_message} after {attempt + 1} attempts: {str(e)}"
                    )
                    raise

                wait_time = self._calculate_wait_time(attempt)
                logger.warning(
                    f"{error_message} (attempt {attempt + 1}/{self.max_retries + 1}): {str(e)}. "
                    f"Retrying in {wait_time:.2f}s..."
                )

                await asyncio.sleep(wait_time)

        # This should never be reached, but included for type safety
        if last_exception:
            raise last_exception
        raise RuntimeError(f"{error_message}: Unknown error")


class ConnectionVerifier:
    """
    Verifies connections to AI services with various health check strategies.

    This class provides utilities to verify that an AI service is reachable
    and functioning correctly before attempting to use it.
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        retry_handler: Optional[RetryHandler] = None
    ):
        """
        Initialize the connection verifier.

        Args:
            connection_manager: Connection manager to use for verification
            retry_handler: Optional retry handler for verification attempts
        """
        self.connection_manager = connection_manager
        self.retry_handler = retry_handler or RetryHandler(max_retries=2)
        self.logger = logging.getLogger(f"{__name__}.ConnectionVerifier")

    async def verify_http_connection(
        self,
        endpoint: str = "/",
        expected_status: int = 200
    ) -> bool:
        """
        Verify HTTP connection by making a request to an endpoint.

        Args:
            endpoint: Endpoint to test
            expected_status: Expected HTTP status code

        Returns:
            True if connection is successful, False otherwise
        """
        async def _verify():
            session = await self.connection_manager.get_session()
            async with session.get(endpoint) as response:
                return response.status == expected_status

        try:
            return await self.retry_handler.execute_with_retry(
                _verify,
                error_message="Connection verification failed"
            )
        except Exception as e:
            logger.error(f"Failed to verify HTTP connection: {str(e)}")
            return False

    async def verify_api_key(
        self,
        test_endpoint: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Verify API key by making a test request.

        Args:
            test_endpoint: Endpoint to test with
            payload: Optional payload to send

        Returns:
            True if API key is valid, False otherwise
        """
        try:
            session = await self.connection_manager.get_session()

            if payload:
                async with session.post(test_endpoint, json=payload) as response:
                    # Accept 2xx status codes as success
                    return 200 <= response.status < 300
            else:
                async with session.get(test_endpoint) as response:
                    return 200 <= response.status < 300

        except Exception as e:
            logger.error(f"API key verification failed: {str(e)}")
            return False


class RateLimiter:
    """
    Simple rate limiter for AI service requests.

    This class helps prevent overwhelming AI services with too many
    concurrent or rapid requests.
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20
    ):
        """
        Initialize the rate limiter.

        Args:
            requests_per_second: Maximum requests per second
            burst_size: Maximum burst size
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        self.logger = logging.getLogger(f"{__name__}.RateLimiter")

    async def acquire(self) -> None:
        """
        Acquire permission to make a request.

        This method blocks until a token is available.
        """
        async with self.lock:
            while self.tokens <= 0:
                # Refill tokens based on time passed
                now = time.time()
                time_passed = now - self.last_update
                self.tokens = min(
                    self.burst_size,
                    self.tokens + time_passed * self.requests_per_second
                )
                self.last_update = now

                # If still no tokens, wait
                if self.tokens <= 0:
                    wait_time = 1.0 / self.requests_per_second
                    await asyncio.sleep(wait_time)

            # Consume a token
            self.tokens -= 1


def retry_on_error(
    max_retries: int = 3,
    initial_wait_ms: int = 1000,
    exponential_base: float = 2.0
):
    """
    Decorator for adding retry logic to async functions.

    Args:
        max_retries: Maximum number of retry attempts
        initial_wait_ms: Initial wait time in milliseconds
        exponential_base: Base for exponential backoff

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            retry_handler = RetryHandler(
                max_retries=max_retries,
                initial_wait_ms=initial_wait_ms,
                exponential_base=exponential_base
            )

            async def operation():
                return await func(*args, **kwargs)

            return await retry_handler.execute_with_retry(
                operation,
                error_message=f"{func.__name__} failed"
            )

        return wrapper
    return decorator
