"""
Metrics Middleware for Request Tracking

Automatically tracks HTTP request metrics for monitoring.
"""

import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics"""
    
    async def dispatch(self, request: Request, call_next):
        # Skip metrics for the metrics endpoints themselves to avoid recursion
        if request.url.path in ['/metrics', '/metrics/json', '/ws/metrics', '/dashboard']:
            return await call_next(request)
        
        # Start timer (use perf_counter for monotonic timing)
        start_time = time.perf_counter()
        
        # Process request
        response = None
        status_code = 500
        # Attempt to resolve a normalized route template to limit label cardinality
        route_template = request.url.path
        try:
            route = request.scope.get('route')
            if route and getattr(route, 'path', None):
                route_template = route.path  # e.g., /items/{id}
        except Exception:
            # Fallback to concrete path
            route_template = request.url.path

        metrics_service = getattr(request.app.state, 'metrics_service', None)
        if metrics_service and getattr(metrics_service, 'enabled', False):
            try:
                metrics_service.http_inprogress.labels(method=request.method, endpoint=route_template).inc()
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
            # Calculate duration
            duration = time.perf_counter() - start_time
            
            # Record metrics if service is available
            if metrics_service:
                try:
                    # Record the request using normalized template
                    endpoint = route_template
                    # Record the request
                    metrics_service.record_request(
                        method=request.method,
                        endpoint=endpoint,
                        status=status_code,
                        duration=duration
                    )
                    # Decrement in-progress
                    try:
                        metrics_service.http_inprogress.labels(method=request.method, endpoint=endpoint).dec()
                    except Exception:
                        pass
                except Exception as e:
                    logger.debug(f"Failed to record metrics: {e}")
        
        return response
