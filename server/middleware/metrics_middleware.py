"""
Metrics Middleware for Request Tracking

Automatically tracks HTTP request metrics for monitoring.
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _build_route_templates(routes, prefix: str = "") -> dict:
    """
    Map id(route) -> full path template for every route in an app.

    FastAPI nests included routers rather than flattening them, so a route's
    own ``path`` is relative to the router that declares it: ``/admin/info``
    is stored as ``/info``. Endpoint-prefix filtering therefore cannot work
    off ``route.path`` alone.

    A router's own prefix is already baked into the paths of the routes it
    declares directly, while ``include_context.prefix`` carries the prefix of
    the *including* router - so accumulating the latter reconstructs the full
    template without double-counting.
    """
    mapping = {}
    for route in routes:
        context = getattr(route, "include_context", None)
        if context is not None:
            sub = getattr(context, "included_router", None)
            if sub is None:
                continue
            mapping.update(_build_route_templates(
                getattr(sub, "routes", []),
                prefix + (getattr(context, "prefix", "") or ""),
            ))
            continue
        nested = getattr(route, "routes", None)
        if nested:  # Mount / sub-application
            mapping.update(_build_route_templates(
                nested, prefix + (getattr(route, "path", "") or "")
            ))
            continue
        template = getattr(route, "path_format", None) or getattr(route, "path", None)
        if template:
            mapping[id(route)] = prefix + template
    return mapping


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track request metrics"""

    def _route_template(self, request: Request) -> str | None:
        """Resolve the matched route's full path template, or None."""
        route = request.scope.get('route')
        if route is None:
            return None

        # Routes are fixed once the app has started, so build the map once.
        templates = getattr(request.app.state, '_metrics_route_templates', None)
        if templates is None:
            try:
                templates = _build_route_templates(request.app.routes)
            except (AttributeError, TypeError, RecursionError) as e:
                logger.debug(f"Failed to map route templates: {e}")
                templates = {}
            request.app.state._metrics_route_templates = templates

        return templates.get(id(route)) or getattr(route, 'path', None)

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
            route_template = self._route_template(request) or "__unmatched_route__"

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
