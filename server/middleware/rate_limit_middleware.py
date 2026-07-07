"""
Rate Limiting Middleware

Protects API endpoints from abuse and DDoS attacks using cache-backed
fixed window rate limiting. Supports dual-key limiting (IP + API key).

Features:
- Fixed window counter algorithm
- IP-based rate limiting for all requests
- Higher limits for authenticated API key requests
- Configurable exclude paths
- Standard X-RateLimit-* response headers
"""

import hashlib
import time
import logging
import threading
from typing import Tuple, Dict, Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from utils.ip_utils import extract_ip, parse_trusted_networks
from utils.middleware_utils import path_is_excluded

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """In-memory fixed-window rate limiter used as fallback when the cache service is unavailable."""

    def __init__(self, cleanup_interval: int = 300):
        self._windows: Dict[str, Tuple[int, int]] = {}  # key -> (count, window_minute)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval

    def is_allowed(self, key: str, limit: int) -> Tuple[bool, int]:
        """Check if a request is allowed and return (allowed, remaining)."""
        now = time.monotonic()
        window_minute = int(now // 60)

        with self._lock:
            # Periodic cleanup of stale entries
            if now - self._last_cleanup > self._cleanup_interval:
                cutoff_window = window_minute - 2  # Evict entries silent for two full 60s windows.
                self._windows = {
                    k: v for k, v in self._windows.items() if v[1] > cutoff_window
                }
                self._last_cleanup = now

            count, stored_minute = self._windows.get(key, (0, window_minute))
            if stored_minute != window_minute:
                count = 0

            if count < limit:
                count += 1
                self._windows[key] = (count, window_minute)
                return True, max(0, limit - count)
            else:
                return False, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Cache-backed rate limiting middleware.

    Uses fixed window counters to track request rates per IP address
    and per API key. Only active when a cache service is enabled.
    """

    def __init__(self, app, config: Dict[str, Any]):
        """
        Initialize rate limit middleware.
        
        Args:
            app: The FastAPI/Starlette application
            config: Application configuration dictionary
        """
        super().__init__(app)

        # Extract rate limiting configuration
        security_config = config.get('security', {}) or {}
        rate_config = security_config.get('rate_limiting', {}) or {}

        self.enabled = rate_config.get('enabled', False)

        # Proxy trust configuration (security feature to prevent IP spoofing)
        self.trust_proxy_headers = rate_config.get('trust_proxy_headers', False)
        self.trusted_proxies = parse_trusted_networks(
            rate_config.get('trusted_proxies', [])
        )
        if self.trust_proxy_headers and not self.trusted_proxies:
            logger.warning(
                "trust_proxy_headers is enabled but trusted_proxies is empty — "
                "proxy headers will be ignored. "
                "Set trusted_proxies to the CIDR(s) of your reverse proxy."
            )

        # IP limits
        ip_limits = rate_config.get('ip_limits', {}) or {}
        self.ip_requests_per_minute = ip_limits.get('requests_per_minute', 60)
        self.ip_requests_per_hour = ip_limits.get('requests_per_hour', 1000)

        # API key limits (higher)
        api_key_limits = rate_config.get('api_key_limits', {}) or {}
        self.api_key_requests_per_minute = api_key_limits.get('requests_per_minute', 120)
        self.api_key_requests_per_hour = api_key_limits.get('requests_per_hour', 5000)

        # Exclude paths
        self.exclude_paths = rate_config.get('exclude_paths', [
            '/health', '/favicon.ico', '/metrics', '/static'
        ])

        # Response configuration
        self.retry_after_seconds = rate_config.get('retry_after_seconds', 60)

        # API key header name
        api_keys_config = config.get('api_keys', {}) or {}
        self.api_key_header = api_keys_config.get('header_name', 'X-API-Key')

        # In-memory fallback rate limiter (activates when the cache service is unavailable)
        self._fallback_limiter = InMemoryRateLimiter()

        logger.info(
            f"Rate limiting middleware initialized: enabled={self.enabled}, "
            f"trust_proxy_headers={self.trust_proxy_headers}, "
            f"IP limits={self.ip_requests_per_minute}/min {self.ip_requests_per_hour}/hr, "
            f"API key limits={self.api_key_requests_per_minute}/min {self.api_key_requests_per_hour}/hr"
        )
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request, with security controls for proxy headers.

        When trust_proxy_headers is False (default), proxy headers are ignored to prevent
        IP spoofing attacks. Only enable trust_proxy_headers when behind a trusted
        reverse proxy.

        When trust_proxy_headers is True and trusted_proxies is configured, proxy headers
        are only accepted if the direct connection comes from a trusted proxy IP.

        Args:
            request: The incoming request

        Returns:
            Client IP address string
        """
        ip, _metadata = extract_ip(
            request,
            trust_proxy=self.trust_proxy_headers,
            trusted_networks=self.trusted_proxies,
        )
        return ip
    
    def _should_skip_rate_limit(self, request: Request) -> bool:
        """
        Check if the request path should be excluded from rate limiting.

        Args:
            request: The incoming request

        Returns:
            True if rate limiting should be skipped
        """
        return path_is_excluded(request.url.path, self.exclude_paths)

    def _hash_identifier(self, prefix: str, identifier: str) -> str:
        """Hash API keys before including them in rate-limit storage keys."""
        if prefix == "apikey":
            return hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return identifier

    async def _check_rate_limit(
        self,
        cache_service,
        identifier: str,
        limit_per_minute: int,
        limit_per_hour: int,
        prefix: str
    ) -> Tuple[bool, int, int, int]:
        """
        Check rate limit for an identifier using a cache-backed fixed window.

        Args:
            cache_service: The cache provider instance (Redis, Memcached, ...)
            identifier: The rate limit key identifier (IP or API key)
            limit_per_minute: Maximum requests per minute
            limit_per_hour: Maximum requests per hour
            prefix: Key prefix ("ip" or "apikey")

        Returns:
            Tuple of (is_allowed, remaining, limit, reset_timestamp)
        """
        current_time = int(time.time())
        current_minute = current_time // 60
        current_hour = current_time // 3600
        storage_identifier = self._hash_identifier(prefix, identifier)

        minute_key = f"ratelimit:{prefix}:min:{current_minute}:{storage_identifier}"
        hour_key = f"ratelimit:{prefix}:hr:{current_hour}:{storage_identifier}"

        try:
            minute_count = await cache_service.increment_with_ttl(minute_key, 60)
            if minute_count <= 0:
                # increment_with_ttl() returns 0 on a cache error/outage rather than
                # raising - treat that the same as an exception so we fail over to
                # the in-memory limiter instead of reading it as "0 requests so far".
                raise RuntimeError("Cache increment returned a non-positive count")

            if minute_count > limit_per_minute:
                reset_time = (current_minute + 1) * 60
                return False, 0, limit_per_minute, reset_time

            hour_count = await cache_service.increment_with_ttl(hour_key, 3600)
            if hour_count <= 0:
                raise RuntimeError("Cache increment returned a non-positive count")

            if hour_count > limit_per_hour:
                reset_time = (current_hour + 1) * 3600
                return False, 0, limit_per_hour, reset_time

            # Calculate remaining (use the more restrictive limit)
            minute_remaining = limit_per_minute - minute_count
            hour_remaining = limit_per_hour - hour_count

            # Use minute window for reset time (more relevant for clients)
            remaining = max(0, min(minute_remaining, hour_remaining))
            reset_time = (current_minute + 1) * 60

            return True, remaining, limit_per_minute, reset_time

        except Exception as e:
            logger.warning(f"Cache-backed rate limit check failed, using in-memory fallback: {e}")
            # Fall back to in-memory rate limiter instead of fail-open
            allowed, remaining = self._fallback_limiter.is_allowed(
                f"{prefix}:{storage_identifier}", limit_per_minute
            )
            reset_time = (current_minute + 1) * 60
            return allowed, remaining, limit_per_minute, reset_time
    
    def _add_rate_limit_headers(
        self,
        response: Response,
        limit: int,
        remaining: int,
        reset_timestamp: int
    ) -> None:
        """
        Add rate limit headers to response.
        
        Args:
            response: The response object
            limit: The rate limit
            remaining: Remaining requests in window
            reset_timestamp: Unix timestamp when window resets
        """
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_timestamp)

    def _rate_limited_response(self, limit: int, remaining: int, reset: int) -> JSONResponse:
        response = JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit exceeded. Please retry after {self.retry_after_seconds} seconds.",
                "retry_after": self.retry_after_seconds
            }
        )
        response.headers["Retry-After"] = str(self.retry_after_seconds)
        self._add_rate_limit_headers(response, limit, remaining, reset)
        return response
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request through rate limiting.
        
        Args:
            request: The incoming request
            call_next: The next middleware/handler
            
        Returns:
            Response object
        """
        # Skip if rate limiting is disabled
        if not self.enabled:
            return await call_next(request)
        
        # Skip excluded paths
        if self._should_skip_rate_limit(request):
            return await call_next(request)
        
        # Check if a cache service is available
        cache_service = getattr(request.app.state, 'cache_service', None)
        if not cache_service or not cache_service.enabled:
            # Cache service not available — use in-memory fallback instead of passing through
            client_ip = self._get_client_ip(request)
            allowed, remaining = self._fallback_limiter.is_allowed(
                f"ip:{client_ip}", self.ip_requests_per_minute
            )
            if not allowed:
                return self._rate_limited_response(
                    self.ip_requests_per_minute,
                    remaining,
                    int(time.time()) + 60,
                )
            response = await call_next(request)
            return response

        # Ensure the cache service is initialized
        if not cache_service.initialized:
            try:
                await cache_service.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize cache service for rate limiting: {e}")
                return await call_next(request)

        # Extract identifiers
        client_ip = self._get_client_ip(request)
        api_key = request.headers.get(self.api_key_header)

        # Check IP rate limit
        ip_allowed, ip_remaining, ip_limit, ip_reset = await self._check_rate_limit(
            cache_service,
            client_ip,
            self.ip_requests_per_minute,
            self.ip_requests_per_hour,
            "ip"
        )

        if not ip_allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return self._rate_limited_response(ip_limit, ip_remaining, ip_reset)

        # If API key is present, also check API key limit
        if api_key:
            key_allowed, key_remaining, key_limit, key_reset = await self._check_rate_limit(
                cache_service,
                api_key,
                self.api_key_requests_per_minute,
                self.api_key_requests_per_hour,
                "apikey"
            )
            
            if not key_allowed:
                logger.warning("Rate limit exceeded for API key")
                return self._rate_limited_response(key_limit, key_remaining, key_reset)
            
            # Use API key limits for headers if authenticated
            limit = key_limit
            remaining = key_remaining
            reset_timestamp = key_reset
        else:
            # Use IP limits for headers
            limit = ip_limit
            remaining = ip_remaining
            reset_timestamp = ip_reset
        
        # Process the request
        response = await call_next(request)
        
        # Add rate limit headers to successful responses
        self._add_rate_limit_headers(response, limit, remaining, reset_timestamp)
        
        return response
