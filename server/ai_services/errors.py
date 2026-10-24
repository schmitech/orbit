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

import logging
from enum import Enum
from typing import Mapping, Optional


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
    "UnauthorizedResponseError": _STATUS_MESSAGES[401],
    "PermissionDeniedError": _STATUS_MESSAGES[403],
    "ForbiddenResponseError": _STATUS_MESSAGES[403],
    "NotFoundError": _STATUS_MESSAGES[404],
    "NotFoundResponseError": _STATUS_MESSAGES[404],
    "RateLimitError": _STATUS_MESSAGES[429],
    "TooManyRequestsResponseError": _STATUS_MESSAGES[429],
    "APITimeoutError": _STATUS_MESSAGES[408],
    "Timeout": _STATUS_MESSAGES[408],
    "TimeoutError": _STATUS_MESSAGES[408],
    "RequestTimeoutResponseError": _STATUS_MESSAGES[408],
    "EdgeNetworkTimeoutResponseError": _STATUS_MESSAGES[408],
    "APIConnectionError": _STATUS_MESSAGES[503],
    "ConnectionError": _STATUS_MESSAGES[503],
    "ServiceUnavailableError": _STATUS_MESSAGES[503],
    "ServiceUnavailableResponseError": _STATUS_MESSAGES[503],
    "ProviderOverloadedResponseError": _STATUS_MESSAGES[503],
    "InternalServerError": _STATUS_MESSAGES[500],
    "InternalServerResponseError": _STATUS_MESSAGES[500],
    "BadRequestError": _STATUS_MESSAGES[400],
    "BadRequestResponseError": _STATUS_MESSAGES[400],
    "UnprocessableEntityError": _STATUS_MESSAGES[422],
    "UnprocessableEntityResponseError": _STATUS_MESSAGES[422],
    "ConflictError": _STATUS_MESSAGES[409],
    "ConflictResponseError": _STATUS_MESSAGES[409],
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
    if response is None:
        response = getattr(error, "raw_response", None)
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


class ErrorCategory(str, Enum):
    """
    A provider error's classification, as determined by the caller.

    Providers classify errors very differently — SDK exception `isinstance`
    checks, substring matching on the error text, structured error codes
    (e.g. boto's `ClientError.response['Error']['Code']`) — and that
    classification logic is inherently provider-specific, so it stays in each
    provider's own `_handle_*_error`. What's duplicated across providers is
    the boilerplate *after* classification: picking a log level, building a
    message, and calling `raise_sanitized`. This enum is the shared vocabulary
    for that boilerplate; see `log_and_raise_sanitized`.
    """

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    CONNECTION = "connection"
    QUOTA = "quota"
    PERMISSION = "permission"
    DEPLOYMENT = "deployment"
    MODEL_NOT_READY = "model_not_ready"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    API = "api"
    UNEXPECTED = "unexpected"


# Categories logged as a warning rather than an error — transient/expected
# conditions (the caller is expected to retry) rather than failures.
_CATEGORY_LOG_LEVEL: dict[ErrorCategory, int] = {
    ErrorCategory.RATE_LIMIT: logging.WARNING,
    ErrorCategory.QUOTA: logging.WARNING,
}

# Default message template per category. `{provider}` and `{operation}` are
# always available; `{error}` is the stringified exception. Callers can pass
# their own `message` to `log_and_raise_sanitized` when a category needs
# wording a generic template can't express (e.g. AWS's structured error code).
_CATEGORY_DEFAULT_MESSAGE: dict[ErrorCategory, str] = {
    ErrorCategory.AUTH: "{provider} authentication failed during {operation}: Invalid API key",
    ErrorCategory.RATE_LIMIT: "{provider} rate limit exceeded during {operation}",
    ErrorCategory.CONNECTION: "{provider} connection error during {operation}: {error}",
    ErrorCategory.QUOTA: "{provider} quota exceeded during {operation}: {error}",
    ErrorCategory.PERMISSION: "{provider} permission error during {operation}: {error}",
    ErrorCategory.DEPLOYMENT: "{provider} deployment error during {operation}: {error}",
    ErrorCategory.MODEL_NOT_READY: "{provider} model not ready during {operation}: {error}",
    ErrorCategory.VALIDATION: "{provider} validation error during {operation}: {error}",
    ErrorCategory.NOT_FOUND: "{provider} model not found during {operation}: {error}",
    ErrorCategory.API: "{provider} API error during {operation}: {error}",
    ErrorCategory.UNEXPECTED: "Unexpected error during {operation}: {error}",
}


def log_and_raise_sanitized(
    logger: logging.Logger,
    error: BaseException,
    *,
    provider: str,
    operation: str,
    category: ErrorCategory,
    message: Optional[str] = None,
    error_text: Optional[str] = None,
    message_fields: Optional[Mapping[str, str]] = None,
    level: Optional[int] = None,
) -> None:
    """
    Log a pre-classified provider error at the right level, then raise it
    sanitized via `raise_sanitized`.

    The caller does its own classification (isinstance checks, substring
    matching, SDK error codes — whatever fits that provider) and passes the
    resulting `category`; this function owns only the log-level lookup,
    default message formatting, and the final `raise_sanitized` call, so
    providers stop re-deriving that boilerplate by hand.

    `message`, if given, MUST be a plain template — never an f-string
    with raw provider/SDK text (an error message, a parsed error code, a
    configured model name, ...) already baked into it. That dynamic text can
    itself contain `{`/`}` (e.g. a JSON body in an error message), and
    pre-baking it into the template means this function's own `.format()`
    call would try to parse it as replacement fields, raising `KeyError`/
    `ValueError` instead of the sanitized error — defeating the whole point
    of this helper. Pass dynamic text through `error_text` or `message_fields`
    instead (substitution values are never re-parsed).

    Args:
        logger: The caller's module logger.
        error: The exception that occurred.
        provider: Provider name (used for both the log message and
            `raise_sanitized`'s client-safe message lookup).
        operation: Operation label (e.g. "chat completion", "embedding query").
        category: The caller's classification of `error`.
        message: Optional override template for the default per-category
            message, for providers whose wording doesn't fit the generic
            template. See the warning above about what may go in it.
        error_text: Optional override for what `{error}` resolves to in the
            template (defaults to `str(error)`) — e.g. a structured SDK
            error's `.message` field rather than its full `str()` form.
        message_fields: Additional named values for the message template,
            such as a structured SDK error code or configured base URL.
        level: Optional override for the log level (defaults to the
            category's usual level — WARNING for rate-limit/quota, ERROR for
            everything else). Use when a provider's classification narrows a
            normally-transient category (e.g. quota) to something that should
            still be logged as an error for that provider.
    """
    log_level = level if level is not None else _CATEGORY_LOG_LEVEL.get(category, logging.ERROR)
    template = message or _CATEGORY_DEFAULT_MESSAGE[category]
    rendered_error = error_text if error_text is not None else str(error)
    fields = dict(message_fields or {})
    fields.update(provider=provider.title(), operation=operation, error=rendered_error)
    logger.log(
        log_level,
        template.format_map(fields),
    )
    raise_sanitized(error, provider=provider, operation=operation)
