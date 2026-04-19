"""
Client-safe error handling for AI services.

Provider SDKs (OpenAI, Anthropic, Google, etc.) raise exceptions whose string
representation often includes internal details: upstream hostnames, raw HTTP
response bodies, header echoes, account identifiers, or IP-level policy
messages. Surfacing ``str(exc)`` directly to end users leaks that detail.

This module provides a single sanitizer that maps any provider exception to a
stable, user-friendly message. Full details remain available for logging via
the original exception, which callers should log separately.
"""

from __future__ import annotations

from typing import Optional


GENERIC_MESSAGE = (
    "The AI service is currently unavailable. Please try again later."
)

# Mapping of HTTP status codes to user-facing messages.
_STATUS_MESSAGES = {
    400: "The request could not be processed. Please rephrase and try again.",
    401: "The AI service is not available due to an authentication issue. "
         "Please contact your administrator.",
    403: "The AI service rejected this request. Please contact your administrator.",
    404: "The configured AI model is unavailable. Please contact your administrator.",
    408: "The AI service took too long to respond. Please try again.",
    409: "The AI service reported a conflict. Please try again.",
    413: "The request is too large for the AI service. Please shorten your input.",
    422: "The request could not be processed. Please rephrase and try again.",
    429: "The AI service is receiving too many requests. Please try again shortly.",
    500: "The AI service encountered an internal error. Please try again later.",
    502: "The AI service is temporarily unreachable. Please try again shortly.",
    503: "The AI service is temporarily unavailable. Please try again shortly.",
    504: "The AI service took too long to respond. Please try again.",
}

# Exception class names mapped to user-facing messages. Using name-based
# matching avoids hard imports on every provider SDK.
_EXCEPTION_NAME_MESSAGES = {
    "AuthenticationError": _STATUS_MESSAGES[401],
    "PermissionDeniedError": _STATUS_MESSAGES[403],
    "NotFoundError": _STATUS_MESSAGES[404],
    "RateLimitError": _STATUS_MESSAGES[429],
    "APITimeoutError": _STATUS_MESSAGES[408],
    "Timeout": _STATUS_MESSAGES[408],
    "TimeoutError": _STATUS_MESSAGES[408],
    "APIConnectionError": _STATUS_MESSAGES[503],
    "ConnectionError": _STATUS_MESSAGES[503],
    "ServiceUnavailableError": _STATUS_MESSAGES[503],
    "InternalServerError": _STATUS_MESSAGES[500],
    "BadRequestError": _STATUS_MESSAGES[400],
    "UnprocessableEntityError": _STATUS_MESSAGES[422],
    "ConflictError": _STATUS_MESSAGES[409],
}


class ProviderServiceError(Exception):
    """
    Exception carrying both the raw provider error (for logging) and a
    sanitized, user-safe message (for client responses).

    Callers that catch this exception should surface ``user_message`` to end
    users and log ``original_error`` separately.
    """

    def __init__(
        self,
        user_message: str,
        *,
        original_error: Optional[BaseException] = None,
        provider: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.original_error = original_error
        self.provider = provider
        self.operation = operation


def _extract_status_code(error: BaseException) -> Optional[int]:
    """Best-effort extraction of an HTTP status code from a provider exception."""
    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    return None


def sanitize_provider_error(
    error: BaseException,
    *,
    provider: Optional[str] = None,
    operation: Optional[str] = None,
) -> str:
    """
    Map a raw provider exception to a client-safe message.

    The returned string never includes raw SDK output, response bodies, or
    other internal details. The full exception should be logged by the caller.

    Args:
        error: The exception raised by the provider SDK.
        provider: Optional provider name used only for message personalization.
        operation: Optional operation label ("generation", "streaming", ...)
            used only for message personalization.

    Returns:
        A stable, user-friendly error message.
    """
    if isinstance(error, ProviderServiceError):
        return error.user_message

    status = _extract_status_code(error)
    if status is not None and status in _STATUS_MESSAGES:
        return _STATUS_MESSAGES[status]

    name = type(error).__name__
    if name in _EXCEPTION_NAME_MESSAGES:
        return _EXCEPTION_NAME_MESSAGES[name]

    # Fall through to the generic message. We deliberately do not include
    # str(error) or any exception attributes to prevent leaking internal
    # details such as IP policy messages, hostnames, or raw API responses.
    return GENERIC_MESSAGE


def raise_sanitized(
    error: BaseException,
    *,
    provider: Optional[str] = None,
    operation: Optional[str] = None,
) -> None:
    """
    Wrap a raw provider exception in ``ProviderServiceError`` and raise it.

    Intended to be called from provider base-class ``_handle_*_error`` helpers
    after logging. The raise replaces a subsequent ``raise`` or
    ``yield f"Error: {str(e)}"`` in the caller, ensuring the raw SDK error
    never reaches the client.
    """
    raise ProviderServiceError(
        sanitize_provider_error(error, provider=provider, operation=operation),
        original_error=error,
        provider=provider,
        operation=operation,
    ) from error
