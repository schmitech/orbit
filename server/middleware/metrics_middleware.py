"""
Metrics Middleware for Request Tracking

Automatically tracks HTTP request metrics for monitoring.
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip metrics for the metrics endpoints themselves to avoid recursion
        if request.url.path in ['/metrics', '/metrics/json', '/ws/metrics']:
            return await call_next(request)
        
        # Start timer (use perf_counter for monotonic timing)
        start_time = time.perf_counter()
        
        metrics_service = getattr(request.app.state, 'metrics_service', None)
        # The route is unknown until call_next() runs routing, so the in-progress gauge
        # can't be labeled per-endpoint without falling back to raw (unbounded) paths.
        # Do not move this inc() after routing to "recover" per-route granularity.
        inprogress_endpoint = "__pending_route__"
        if metrics_service and getattr(metrics_service, 'enabled', False):
            try:
                metrics_service.http_inprogress.labels(method=request.method, endpoint=inprogress_endpoint).inc()
            except Exception:
                pass
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.error(f"Request failed: {e}")
            status_code = 500
            raise
        finally:
            # Route matching happens inside call_next(); read the route only after it runs
            # so parameterized paths are recorded as templates instead of raw URL paths.
            route = request.scope.get('route')
            route_template = getattr(route, 'path', None) or "__unmatched_route__"

            # Calculate duration
            duration = time.perf_counter() - start_time
            
            # Record metrics if service is available
            if metrics_service and getattr(metrics_service, 'enabled', False):
                try:
                    # Record the request
                    metrics_service.record_request(
                        method=request.method,
                        endpoint=route_template,
                        status=status_code,
                        duration=duration
                    )
                    # Decrement in-progress
                    try:
                        metrics_service.http_inprogress.labels(method=request.method, endpoint=inprogress_endpoint).dec()
                    except Exception:
                        pass
                except Exception as e:
                    logger.debug(f"Failed to record metrics: {e}")
        
        return response
