"""
Throttle Middleware
===================

Protects API endpoints by progressively delaying requests as quota usage
approaches limits. Works alongside rate limiting to provide smoother
traffic control and better user experience.

Features:
- Progressive delay based on quota usage percentage
- Per-API-key daily/monthly quotas
- Priority-based delay multipliers
- Exponential or linear delay curves
- Standard X-Quota-* response headers
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ThrottleMiddleware(BaseHTTPMiddleware):
    """
    Quota-based throttle middleware.

    Delays requests progressively as quota usage increases, providing
    smoother rate control than hard rejection. Only active when throttling
    is enabled and Redis is available.
    """

    def __init__(self, app, config: Dict[str, Any]):
        """
        Initialize throttle middleware.

        Args:
            app: The FastAPI/Starlette application
            config: Application configuration dictionary
        """
        super().__init__(app)
        self.config = config

        # Extract throttling configuration
        security_config = config.get('security', {}) or {}
        throttle_config = security_config.get('throttling', {}) or {}

        self.enabled = throttle_config.get('enabled', False)

        # Default quotas
        default_quotas = throttle_config.get('default_quotas', {}) or {}
        self.default_daily_limit = default_quotas.get('daily_limit', 10000)
        self.default_monthly_limit = default_quotas.get('monthly_limit', 100000)

        # Delay configuration
        delay_config = throttle_config.get('delay', {}) or {}
        self.min_delay_ms = delay_config.get('min_ms', 100)
        self.max_delay_ms = delay_config.get('max_ms', 5000)
        self.delay_curve = delay_config.get('curve', 'exponential')
        self.threshold_percent = delay_config.get('threshold_percent', 70) / 100.0

        # Priority multipliers
        self.priority_multipliers = throttle_config.get('priority_multipliers', {
            1: 0.5,
            5: 1.0,
            10: 2.0
        })

        # Exclude paths (inherit from rate limiting + custom)
        rate_limit_config = security_config.get('rate_limiting', {}) or {}
        rate_limit_exclude = rate_limit_config.get('exclude_paths', [])
        throttle_exclude = throttle_config.get('exclude_paths', [])
        self.exclude_paths = list(set(rate_limit_exclude + throttle_exclude))

        # Header names
        headers_config = throttle_config.get('headers', {}) or {}
        self.header_delay = headers_config.get('delay', 'X-Throttle-Delay')
        self.header_daily_remaining = headers_config.get('daily_remaining', 'X-Quota-Daily-Remaining')
        self.header_monthly_remaining = headers_config.get('monthly_remaining', 'X-Quota-Monthly-Remaining')
        self.header_daily_reset = headers_config.get('daily_reset', 'X-Quota-Daily-Reset')
        self.header_monthly_reset = headers_config.get('monthly_reset', 'X-Quota-Monthly-Reset')

        # API key header name
        api_keys_config = config.get('api_keys', {}) or {}
        self.api_key_header = api_keys_config.get('header_name', 'X-API-Key')

        logger.info(
            f"Throttle middleware initialized: enabled={self.enabled}, "
            f"delay={self.min_delay_ms}-{self.max_delay_ms}ms, "
            f"curve={self.delay_curve}, threshold={self.threshold_percent*100}%"
        )

    def _get_api_key(self, request: Request) -> Optional[str]:
        """
        Extract API key from request header if present.

        Args:
            request: The incoming request

        Returns:
            API key string or None
        """
        return request.headers.get(self.api_key_header)

    def _should_skip_throttle(self, request: Request) -> bool:
        """
        Check if the request path should be excluded from throttling.

        Args:
            request: The incoming request

        Returns:
            True if throttling should be skipped
        """
        path = request.url.path

        for exclude_path in self.exclude_paths:
            if path == exclude_path or path.startswith(exclude_path + '/'):
                return True

        return False

    def _get_priority_multiplier(self, priority: int) -> float:
        """
        Get delay multiplier for a given priority level.

        Args:
            priority: Priority level 1-10

        Returns:
            Delay multiplier
        """
        # Try exact match first
        if priority in self.priority_multipliers:
            return self.priority_multipliers[priority]

        # Interpolate between known values
        known_priorities = sorted(self.priority_multipliers.keys())

        if priority <= known_priorities[0]:
            return self.priority_multipliers[known_priorities[0]]
        if priority >= known_priorities[-1]:
            return self.priority_multipliers[known_priorities[-1]]

        # Find surrounding values and interpolate
        for i, p in enumerate(known_priorities[:-1]):
            if p <= priority <= known_priorities[i + 1]:
                lower_p = p
                upper_p = known_priorities[i + 1]
                lower_mult = self.priority_multipliers[lower_p]
                upper_mult = self.priority_multipliers[upper_p]
                ratio = (priority - lower_p) / (upper_p - lower_p)
                return lower_mult + (upper_mult - lower_mult) * ratio

        return 1.0

    def _calculate_usage_percentage(
        self,
        daily_used: int,
        daily_limit: Optional[int],
        monthly_used: int,
        monthly_limit: Optional[int]
    ) -> float:
        """
        Calculate the highest usage percentage.

        Args:
            daily_used: Current daily usage
            daily_limit: Daily limit (None = unlimited)
            monthly_used: Current monthly usage
            monthly_limit: Monthly limit (None = unlimited)

        Returns:
            Usage percentage (0.0 to 1.0+)
        """
        percentages = []

        if daily_limit is not None and daily_limit > 0:
            percentages.append(daily_used / daily_limit)

        if monthly_limit is not None and monthly_limit > 0:
            percentages.append(monthly_used / monthly_limit)

        if not percentages:
            return 0.0

        return max(percentages)

    def _calculate_delay(
        self,
        usage_pct: float,
        priority: int
    ) -> int:
        """
        Calculate throttle delay based on usage percentage and priority.

        Args:
            usage_pct: Usage percentage (0.0 to 1.0+)
            priority: Priority level 1-10

        Returns:
            Delay in milliseconds
        """
        # No delay if below threshold
        if usage_pct < self.threshold_percent:
            return 0

        # Normalize to 0-1 range above threshold
        if usage_pct >= 1.0:
            normalized = 1.0
        else:
            normalized = (usage_pct - self.threshold_percent) / (1.0 - self.threshold_percent)
            normalized = max(0.0, min(1.0, normalized))

        # Calculate base delay using curve
        if self.delay_curve == 'exponential':
            # Exponential curve: delay increases faster as usage approaches limit
            delay_factor = normalized ** 2
        else:
            # Linear curve
            delay_factor = normalized

        base_delay = self.min_delay_ms + (self.max_delay_ms - self.min_delay_ms) * delay_factor

        # Apply priority multiplier
        multiplier = self._get_priority_multiplier(priority)
        final_delay = int(base_delay * multiplier)

        # Cap at max delay
        return min(final_delay, self.max_delay_ms * 2)

    def _add_quota_headers(
        self,
        response: Response,
        delay_ms: int,
        daily_remaining: Optional[int],
        monthly_remaining: Optional[int],
        daily_reset_at: float,
        monthly_reset_at: float
    ) -> None:
        """
        Add quota headers to response.

        Args:
            response: The response object
            delay_ms: Delay applied in milliseconds
            daily_remaining: Requests remaining today (None if unlimited)
            monthly_remaining: Requests remaining this month (None if unlimited)
            daily_reset_at: Unix timestamp of daily reset
            monthly_reset_at: Unix timestamp of monthly reset
        """
        response.headers[self.header_delay] = str(delay_ms)

        if daily_remaining is not None:
            response.headers[self.header_daily_remaining] = str(daily_remaining)
        response.headers[self.header_daily_reset] = str(int(daily_reset_at))

        if monthly_remaining is not None:
            response.headers[self.header_monthly_remaining] = str(monthly_remaining)
        response.headers[self.header_monthly_reset] = str(int(monthly_reset_at))

    async def dispatch(self, request: Request, call_next):
        """
        Process request through throttling.

        Args:
            request: The incoming request
            call_next: The next middleware/handler

        Returns:
            Response object
        """
        # Skip if throttling is disabled
        if not self.enabled:
            return await call_next(request)

        # Skip excluded paths
        if self._should_skip_throttle(request):
            return await call_next(request)

        # Get API key - throttling only applies to authenticated requests
        api_key = self._get_api_key(request)
        if not api_key:
            # No API key, pass through (rate limiting will handle it)
            return await call_next(request)

        # Check if quota service is available
        quota_service = getattr(request.app.state, 'quota_service', None)
        if not quota_service or not quota_service.enabled:
            # Quota service not available, pass through
            return await call_next(request)

        try:
            # Get quota config for this API key
            quota_config = await quota_service.get_quota_config(api_key)

            # Check if throttling is disabled for this key
            if not quota_config.get('throttle_enabled', True):
                return await call_next(request)

            # Increment usage and get current counts
            daily_used, monthly_used, daily_reset_seconds, monthly_reset_seconds = \
                await quota_service.increment_usage(api_key)

            # Get limits
            daily_limit = quota_config.get('daily_limit')
            monthly_limit = quota_config.get('monthly_limit')
            priority = quota_config.get('throttle_priority', 5)

            # Calculate remaining
            daily_remaining = None if daily_limit is None else max(0, daily_limit - daily_used)
            monthly_remaining = None if monthly_limit is None else max(0, monthly_limit - monthly_used)

            # Calculate reset timestamps
            daily_reset_at = time.time() + daily_reset_seconds
            monthly_reset_at = time.time() + monthly_reset_seconds

            # Check if quota is exceeded (hard limit)
            quota_exceeded = False
            exceeded_type = None

            if daily_limit is not None and daily_used > daily_limit:
                quota_exceeded = True
                exceeded_type = 'daily'
            elif monthly_limit is not None and monthly_used > monthly_limit:
                quota_exceeded = True
                exceeded_type = 'monthly'

            if quota_exceeded:
                logger.warning(f"Quota exceeded for API key ({exceeded_type}): {api_key[:8]}...")
                response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Quota exceeded ({exceeded_type}). Please wait for quota reset.",
                        "quota_exceeded": exceeded_type,
                        "daily_remaining": daily_remaining,
                        "monthly_remaining": monthly_remaining,
                        "daily_reset_at": int(daily_reset_at),
                        "monthly_reset_at": int(monthly_reset_at)
                    }
                )
                self._add_quota_headers(
                    response, 0, daily_remaining, monthly_remaining,
                    daily_reset_at, monthly_reset_at
                )
                return response

            # Calculate usage percentage and delay
            usage_pct = self._calculate_usage_percentage(
                daily_used, daily_limit, monthly_used, monthly_limit
            )
            delay_ms = self._calculate_delay(usage_pct, priority)

            # Apply delay if needed
            if delay_ms > 0:
                logger.debug(
                    f"Throttling API key {api_key[:8]}...: "
                    f"usage={usage_pct*100:.1f}%, delay={delay_ms}ms"
                )
                await asyncio.sleep(delay_ms / 1000.0)

            # Process the request
            response = await call_next(request)

            # Add quota headers to successful responses
            self._add_quota_headers(
                response, delay_ms, daily_remaining, monthly_remaining,
                daily_reset_at, monthly_reset_at
            )

            return response

        except Exception as e:
            logger.warning(f"Throttle middleware error, allowing request: {e}")
            # Fail-open: allow the request through on any error
            return await call_next(request)
