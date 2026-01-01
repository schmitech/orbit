"""
Rate Limiting Middleware

Protects API endpoints from abuse and DDoS attacks using Redis-backed
fixed window rate limiting. Supports dual-key limiting (IP + API key).

Features:
- Fixed window counter algorithm
- IP-based rate limiting for all requests
- Higher limits for authenticated API key requests
- Configurable exclude paths
- Standard X-RateLimit-* response headers
"""

import time
import logging
import ipaddress
from typing import Optional, Tuple, Dict, Any, List
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed rate limiting middleware.

    Uses fixed window counters to track request rates per IP address
    and per API key. Only active when Redis is enabled.
    """

    # Lua script for atomic increment with expiration
    # Prevents race condition where key is incremented but expire fails
    _INCR_WITH_EXPIRE_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

    def __init__(self, app, config: Dict[str, Any]):
        """
        Initialize rate limit middleware.
        
        Args:
            app: The FastAPI/Starlette application
            config: Application configuration dictionary
        """
        super().__init__(app)
        self.config = config

        # Extract rate limiting configuration
        security_config = config.get('security', {}) or {}
        rate_config = security_config.get('rate_limiting', {}) or {}

        self.enabled = rate_config.get('enabled', False)

        # Proxy trust configuration (security feature to prevent IP spoofing)
        self.trust_proxy_headers = rate_config.get('trust_proxy_headers', False)
        self.trusted_proxies = self._parse_trusted_proxies(
            rate_config.get('trusted_proxies', [])
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

        # Registered Lua script (initialized lazily when Redis is available)
        self._incr_script = None

        logger.info(
            f"Rate limiting middleware initialized: enabled={self.enabled}, "
            f"trust_proxy_headers={self.trust_proxy_headers}, "
            f"IP limits={self.ip_requests_per_minute}/min {self.ip_requests_per_hour}/hr, "
            f"API key limits={self.api_key_requests_per_minute}/min {self.api_key_requests_per_hour}/hr"
        )
    
    def _parse_trusted_proxies(self, proxies: List[str]) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """
        Parse trusted proxy IP addresses/CIDRs into network objects.

        Args:
            proxies: List of IP addresses or CIDR notations

        Returns:
            List of parsed network objects
        """
        networks = []
        for proxy in proxies:
            try:
                # Try to parse as a network (CIDR notation)
                network = ipaddress.ip_network(proxy, strict=False)
                networks.append(network)
            except ValueError as e:
                logger.warning(f"Invalid trusted proxy address '{proxy}': {e}")
        return networks

    def _is_trusted_proxy(self, ip: str) -> bool:
        """
        Check if an IP address is in the trusted proxies list.

        Args:
            ip: IP address to check

        Returns:
            True if the IP is trusted, False otherwise
        """
        if not self.trusted_proxies:
            # If no trusted proxies configured, trust all (when trust_proxy_headers is True)
            return True

        try:
            addr = ipaddress.ip_address(ip)
            for network in self.trusted_proxies:
                if addr in network:
                    return True
        except ValueError:
            pass

        return False

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
        # Get the direct connection IP
        direct_ip = request.client.host if request.client else None

        # If proxy headers are not trusted, use direct IP only
        if not self.trust_proxy_headers:
            if direct_ip:
                return direct_ip
            return "unknown"

        # If trusted_proxies is configured, verify the direct connection is from a trusted proxy
        if self.trusted_proxies and direct_ip:
            if not self._is_trusted_proxy(direct_ip):
                # Direct connection is not from a trusted proxy, ignore proxy headers
                logger.debug(
                    f"Ignoring proxy headers from untrusted IP {direct_ip}"
                )
                return direct_ip

        # Trust proxy headers - check X-Forwarded-For first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(',')[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client IP
        if direct_ip:
            return direct_ip

        return "unknown"
    
    def _get_api_key(self, request: Request) -> Optional[str]:
        """
        Extract API key from request header if present.
        
        Args:
            request: The incoming request
            
        Returns:
            API key string or None
        """
        return request.headers.get(self.api_key_header)
    
    def _should_skip_rate_limit(self, request: Request) -> bool:
        """
        Check if the request path should be excluded from rate limiting.

        Args:
            request: The incoming request

        Returns:
            True if rate limiting should be skipped
        """
        path = request.url.path

        for exclude_path in self.exclude_paths:
            if path == exclude_path or path.startswith(exclude_path + '/'):
                return True

        return False

    def _register_lua_script(self, redis_service) -> None:
        """Register Lua script with Redis client for efficient execution."""
        if not redis_service or not redis_service.client:
            return

        try:
            self._incr_script = redis_service.client.register_script(
                self._INCR_WITH_EXPIRE_SCRIPT
            )
            logger.debug("Registered rate limit Lua script with Redis")
        except Exception as e:
            logger.warning(f"Failed to register Lua script: {e}")
            self._incr_script = None
    
    async def _check_rate_limit(
        self,
        redis_service,
        identifier: str,
        limit_per_minute: int,
        limit_per_hour: int,
        prefix: str
    ) -> Tuple[bool, int, int, int]:
        """
        Check rate limit for an identifier using Redis fixed window.
        
        Args:
            redis_service: The Redis service instance
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
        
        # Redis keys for minute and hour windows
        minute_key = f"ratelimit:{prefix}:min:{current_minute}:{identifier}"
        hour_key = f"ratelimit:{prefix}:hr:{current_hour}:{identifier}"

        try:
            # Register script if not already done
            if self._incr_script is None:
                self._register_lua_script(redis_service)

            if self._incr_script is None:
                logger.warning("Lua script not registered, allowing request")
                return True, limit_per_minute, limit_per_minute, current_time + 60

            # Check minute limit using atomic Lua script
            minute_count = await self._incr_script(
                keys=[minute_key],
                args=[60]  # TTL in seconds
            )

            if minute_count > limit_per_minute:
                # Minute limit exceeded
                reset_time = (current_minute + 1) * 60
                remaining = 0
                return False, remaining, limit_per_minute, reset_time

            # Check hour limit using atomic Lua script
            hour_count = await self._incr_script(
                keys=[hour_key],
                args=[3600]  # TTL in seconds
            )

            if hour_count > limit_per_hour:
                # Hour limit exceeded
                reset_time = (current_hour + 1) * 3600
                remaining = 0
                return False, remaining, limit_per_hour, reset_time
            
            # Calculate remaining (use the more restrictive limit)
            minute_remaining = limit_per_minute - minute_count
            hour_remaining = limit_per_hour - hour_count
            
            # Use minute window for headers (more relevant for clients)
            remaining = max(0, minute_remaining)
            reset_time = (current_minute + 1) * 60
            
            return True, remaining, limit_per_minute, reset_time
            
        except Exception as e:
            logger.warning(f"Rate limit check failed, allowing request: {e}")
            # On Redis error, allow the request (fail-open)
            return True, limit_per_minute, limit_per_minute, current_time + 60
    
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
        
        # Check if Redis service is available
        redis_service = getattr(request.app.state, 'redis_service', None)
        if not redis_service or not redis_service.enabled:
            # Redis not available, pass through without limiting
            return await call_next(request)
        
        # Ensure Redis is initialized
        if not redis_service.initialized:
            try:
                await redis_service.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize Redis for rate limiting: {e}")
                return await call_next(request)
        
        # Extract identifiers
        client_ip = self._get_client_ip(request)
        api_key = self._get_api_key(request)
        
        # Check IP rate limit
        ip_allowed, ip_remaining, ip_limit, ip_reset = await self._check_rate_limit(
            redis_service,
            client_ip,
            self.ip_requests_per_minute,
            self.ip_requests_per_hour,
            "ip"
        )
        
        if not ip_allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Please retry after {self.retry_after_seconds} seconds.",
                    "retry_after": self.retry_after_seconds
                }
            )
            response.headers["Retry-After"] = str(self.retry_after_seconds)
            self._add_rate_limit_headers(response, ip_limit, ip_remaining, ip_reset)
            return response
        
        # If API key is present, also check API key limit
        if api_key:
            key_allowed, key_remaining, key_limit, key_reset = await self._check_rate_limit(
                redis_service,
                api_key,
                self.api_key_requests_per_minute,
                self.api_key_requests_per_hour,
                "apikey"
            )
            
            if not key_allowed:
                logger.warning("Rate limit exceeded for API key")
                response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded. Please retry after {self.retry_after_seconds} seconds.",
                        "retry_after": self.retry_after_seconds
                    }
                )
                response.headers["Retry-After"] = str(self.retry_after_seconds)
                self._add_rate_limit_headers(response, key_limit, key_remaining, key_reset)
                return response
            
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

