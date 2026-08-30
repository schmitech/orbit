"""Login-specific fixed-window rate limiting.

The coarse IP bucket is consumed before authentication. The identity bucket is
consumed only when authentication has failed, so successful sign-ins never use
up a user's failure allowance.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from middleware.rate_limit_middleware import InMemoryRateLimiter
from utils.ip_utils import extract_ip, parse_trusted_networks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginRateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_timestamp: int
    retry_after: int
    bucket: str


class LoginRateLimiter:
    """Cache-backed login limiter with an in-process degraded-mode fallback."""

    def __init__(self, config: Dict[str, Any]):
        auth_config = config.get("auth", {}) or {}
        limit_config = auth_config.get("login_rate_limit", {}) or {}
        self.enabled = bool(limit_config.get("enabled", False))
        self.window_seconds = max(1, int(limit_config.get("window_seconds", 60)))
        self.max_attempts_per_ip = max(
            1, int(limit_config.get("max_attempts_per_ip", 10))
        )
        self.max_attempts_per_username = max(
            1, int(limit_config.get("max_attempts_per_username", 5))
        )
        self.lockout_after_username_limit = bool(
            limit_config.get("lockout_after_username_limit", False)
        )

        rate_config = (config.get("security", {}) or {}).get(
            "rate_limiting", {}
        ) or {}
        self.trust_proxy_headers = bool(
            rate_config.get("trust_proxy_headers", False)
        )
        self.trusted_proxies = parse_trusted_networks(
            rate_config.get("trusted_proxies", [])
        )
        self._fallback_limiter = InMemoryRateLimiter()

    def client_ip(self, request: Request) -> str:
        ip, _ = extract_ip(
            request,
            trust_proxy=self.trust_proxy_headers,
            trusted_networks=self.trusted_proxies,
        )
        return ip

    async def check_ip(self, request: Request) -> LoginRateLimitResult:
        """Consume one attempt from the request IP's coarse login bucket."""
        return await self._consume(
            request, "ip", self.client_ip(request), self.max_attempts_per_ip
        )

    async def record_username_failure(
        self, request: Request, username: str
    ) -> LoginRateLimitResult:
        """Consume one failure for a normalized identity."""
        normalized = (username or "").strip().lower()
        return await self._consume(
            request, "username", normalized, self.max_attempts_per_username
        )

    async def check_username(
        self, request: Request, username: str
    ) -> LoginRateLimitResult:
        """Check an identity's failure bucket without consuming an attempt."""
        normalized = (username or "").strip().lower()
        return await self._check_current_count(
            request,
            "username",
            normalized,
            self.max_attempts_per_username,
        )

    def _window_state(self) -> tuple[int, int, int]:
        now = int(time.time())
        window = now // self.window_seconds
        reset = (window + 1) * self.window_seconds
        return window, reset, max(1, reset - now)

    async def _check_current_count(
        self, request: Request, bucket: str, identifier: str, limit: int
    ) -> LoginRateLimitResult:
        window, reset, retry_after = self._window_state()
        if not self.enabled:
            return LoginRateLimitResult(
                True, limit, limit, reset, retry_after, bucket
            )

        cache_key = f"login:{bucket}:{window}:{identifier}"
        fallback_key = f"login:{bucket}:{identifier}"
        cache_service = getattr(request.app.state, "cache_service", None)
        if cache_service and getattr(cache_service, "enabled", False):
            try:
                if not getattr(cache_service, "initialized", False):
                    await cache_service.initialize()
                raw_count = await cache_service.get(cache_key)
                count = int(raw_count) if raw_count is not None else 0
                return LoginRateLimitResult(
                    count < limit,
                    limit,
                    max(0, limit - count),
                    reset,
                    retry_after,
                    bucket,
                )
            except Exception as exc:
                logger.warning(
                    "Login rate-limit cache read failed; using in-memory fallback: %s",
                    exc,
                )

        count = self._fallback_limiter.get_count(
            fallback_key, self.window_seconds
        )
        return LoginRateLimitResult(
            count < limit,
            limit,
            max(0, limit - count),
            reset,
            retry_after,
            bucket,
        )

    async def _consume(
        self, request: Request, bucket: str, identifier: str, limit: int
    ) -> LoginRateLimitResult:
        window, reset, retry_after = self._window_state()

        if not self.enabled:
            return LoginRateLimitResult(
                True, limit, limit, reset, retry_after, bucket
            )

        cache_key = f"login:{bucket}:{window}:{identifier}"
        fallback_key = f"login:{bucket}:{identifier}"
        cache_service = getattr(request.app.state, "cache_service", None)

        if cache_service and getattr(cache_service, "enabled", False):
            try:
                if not getattr(cache_service, "initialized", False):
                    await cache_service.initialize()
                count = await cache_service.increment_with_ttl(
                    cache_key, self.window_seconds
                )
                if count <= 0:
                    raise RuntimeError(
                        "Cache increment returned a non-positive count"
                    )
                return LoginRateLimitResult(
                    count <= limit,
                    limit,
                    max(0, limit - count),
                    reset,
                    retry_after,
                    bucket,
                )
            except Exception as exc:
                logger.warning(
                    "Login rate-limit cache failed; using in-memory fallback: %s",
                    exc,
                )

        allowed, remaining = self._fallback_limiter.is_allowed(
            fallback_key, limit, self.window_seconds
        )
        return LoginRateLimitResult(
            allowed, limit, remaining, reset, retry_after, bucket
        )


def get_login_rate_limiter(request: Request) -> LoginRateLimiter:
    """Return the application's shared limiter, creating it on first use."""
    limiter = getattr(request.app.state, "login_rate_limiter", None)
    if limiter is None:
        limiter = LoginRateLimiter(getattr(request.app.state, "config", {}) or {})
        request.app.state.login_rate_limiter = limiter
    return limiter


def login_rate_limited_response(result: LoginRateLimitResult) -> JSONResponse:
    """Build the standard 429 response used by all login surfaces."""
    response = JSONResponse(
        status_code=429,
        content={
            "detail": (
                "Too many login attempts. "
                f"Please retry after {result.retry_after} seconds."
            ),
            "retry_after": result.retry_after,
        },
    )
    response.headers["Retry-After"] = str(result.retry_after)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_timestamp)
    return response


async def audit_login_rate_limit(
    request: Request, identity: str | None = None
) -> None:
    """Write a throttled GET/SSO attempt through the admin audit service."""
    audit_service = getattr(request.app.state, "audit_service", None)
    if not audit_service or not getattr(
        audit_service, "admin_events_enabled", False
    ):
        return

    try:
        from services.audit import AdminAuditRecord

        limiter = get_login_rate_limiter(request)
        ip, ip_metadata = extract_ip(
            request,
            trust_proxy=limiter.trust_proxy_headers,
            trusted_networks=limiter.trusted_proxies,
        )
        await audit_service.log_admin_event(
            AdminAuditRecord(
                timestamp=datetime.now(),
                event_type="auth.login.rate_limited",
                action="LOGIN",
                resource_type="session",
                method=request.method,
                path=request.url.path,
                status_code=429,
                success=False,
                ip=ip,
                ip_metadata=ip_metadata,
                actor_type="anonymous",
                user_agent=request.headers.get("user-agent"),
                error_message="HTTP 429",
                request_summary=(
                    {"identity": identity.lower()} if identity else None
                ),
            )
        )
    except Exception:
        logger.exception("Failed to audit a login rate-limit event")
