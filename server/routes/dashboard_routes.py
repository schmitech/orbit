"""
Dashboard Routes for Real-time Monitoring

Provides web-based dashboard and metrics endpoints.
"""

import asyncio
import base64
import logging
from http.cookies import SimpleCookie
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path

logger = logging.getLogger(__name__)


def get_metrics_service(request: Request):
    """Get metrics service from app state"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service:
        raise HTTPException(status_code=503, detail="Metrics service not available")
    if not metrics_service.is_enabled():
        raise HTTPException(status_code=503, detail="Monitoring is disabled")
    return metrics_service

def get_metrics_service_for_dashboard(request: Request):
    """Get metrics service for dashboard endpoints"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service or not metrics_service.is_dashboard_enabled():
        raise HTTPException(status_code=503, detail="Dashboard is disabled")
    return metrics_service

def get_metrics_service_for_prometheus(request: Request):
    """Get metrics service for Prometheus endpoints"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service or not metrics_service.is_prometheus_enabled():
        raise HTTPException(status_code=503, detail="Prometheus metrics are disabled")
    return metrics_service


def get_adapter_manager(request: Request):
    """Get adapter manager from app state"""
    manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request.app.state, 'adapter_manager', None)
    return manager

# Load template at module level
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_dashboard_html_cache = None
_dashboard_template_mtime: Optional[float] = None
_dashboard_static_versions: Dict[str, str] = {}
BASIC_AUTH_REALM = 'Basic realm="ORBIT Dashboard"'
basic_auth = HTTPBasic(auto_error=False)

async def require_dashboard_admin(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(basic_auth)
):
    """Require HTTP Basic admin credentials to access dashboard resources."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": BASIC_AUTH_REALM}
        )

    auth_service = getattr(request.app.state, 'auth_service', None)
    if not auth_service:
        raise HTTPException(status_code=503, detail="Authentication service not available")

    if not getattr(auth_service, "_initialized", True):
        await auth_service.initialize()

    success, user_info = await auth_service.verify_credentials(credentials.username, credentials.password)
    if not success or not user_info or user_info.get("role") != "admin":
        raise HTTPException(
            status_code=401,
            detail="Admin credentials required",
            headers={"WWW-Authenticate": BASIC_AUTH_REALM}
        )

    return {
        "user": user_info,
        "credentials": credentials
    }

def _load_dashboard_template() -> str:
    """Load dashboard HTML template with simple change detection."""
    global _dashboard_html_cache, _dashboard_template_mtime, _dashboard_static_versions
    template_path = TEMPLATE_DIR / "dashboard.html"
    try:
        current_mtime = template_path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Dashboard template not found at %s", template_path)
        return "<h1>Dashboard template missing</h1>"

    static_files = {
        "{{DASHBOARD_TAILWIND_VERSION}}": TEMPLATE_DIR / "dashboard.tailwind.generated.css",
        "{{DASHBOARD_CUSTOM_VERSION}}": TEMPLATE_DIR / "dashboard.css",
        "{{DASHBOARD_JS_VERSION}}": TEMPLATE_DIR / "dashboard.js",
    }

    reload_required = _dashboard_html_cache is None or _dashboard_template_mtime != current_mtime
    new_versions: Dict[str, str] = {}
    for placeholder, path in static_files.items():
        try:
            version = str(path.stat().st_mtime)
        except FileNotFoundError:
            version = "0"
        new_versions[placeholder] = version
        if not reload_required and _dashboard_static_versions.get(placeholder) != version:
            reload_required = True

    if reload_required:
        html = template_path.read_text()
        for placeholder, version in new_versions.items():
            html = html.replace(placeholder, version)
        _dashboard_html_cache = html
        _dashboard_template_mtime = current_mtime
        _dashboard_static_versions = new_versions

    return _dashboard_html_cache

async def _authenticate_websocket_admin(websocket: WebSocket) -> bool:
    """Validate dashboard auth for the metrics WebSocket."""
    auth_service = getattr(websocket.app.state, 'auth_service', None)
    if not auth_service:
        await websocket.close(code=1011, reason="Authentication service unavailable")
        return False

    if not getattr(auth_service, "_initialized", True):
        await auth_service.initialize()

    # Try cookie-based session first
    cookie_header = websocket.headers.get('cookie')
    if cookie_header:
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            if "dashboard_token" in cookie:
                token = cookie["dashboard_token"].value
                valid, user_info = await auth_service.validate_token(token)
                if valid and user_info and user_info.get("role") == "admin":
                    return True
        except Exception:
            pass

    # Fall back to HTTP Basic credentials supplied with the websocket request
    auth_header = websocket.headers.get('authorization')
    if not auth_header or not auth_header.lower().startswith('basic '):
        await websocket.close(code=4401, reason="Authentication required")
        return False

    try:
        decoded = base64.b64decode(auth_header.split(' ', 1)[1]).decode('utf-8')
        username, password = decoded.split(':', 1)
    except Exception:
        await websocket.close(code=4401, reason="Invalid basic auth header")
        return False

    success, user_info = await auth_service.verify_credentials(username, password)
    if not success or not user_info or user_info.get("role") != "admin":
        await websocket.close(code=4403, reason="Admin credentials required")
        return False

    return True

def create_dashboard_router() -> APIRouter:
    """Create dashboard router with monitoring endpoints"""
    
    router = APIRouter(tags=["dashboard"])
    
    # Store active WebSocket connections
    active_connections: list[WebSocket] = []

    @router.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard(
        request: Request,
        metrics_service = Depends(get_metrics_service_for_dashboard),
        auth_context = Depends(require_dashboard_admin)
    ):
        """Serve the monitoring dashboard"""
        html = _load_dashboard_template()
        response = HTMLResponse(content=html)

        auth_service = getattr(request.app.state, 'auth_service', None)
        if auth_service:
            credentials = auth_context.get("credentials")
            existing_token = request.cookies.get("dashboard_token")
            token_valid = False
            if existing_token:
                valid, user_info = await auth_service.validate_token(existing_token)
                token_valid = valid and user_info and user_info.get("role") == "admin"

            if not token_valid and credentials:
                success, token, _ = await auth_service.authenticate_user(credentials.username, credentials.password)
                if success and token:
                    secure_cookie = request.url.scheme == "https"
                    response.set_cookie(
                        "dashboard_token",
                        token,
                        httponly=True,
                        secure=secure_cookie,
                        samesite="lax",
                        max_age=int(getattr(auth_service, "session_duration_hours", 12) * 3600)
                    )

        return response
    
    @router.websocket("/ws/metrics")
    async def websocket_metrics(websocket: WebSocket):
        """WebSocket endpoint for real-time metrics streaming"""
        if not await _authenticate_websocket_admin(websocket):
            return

        await websocket.accept()
        active_connections.append(websocket)
        # Track websocket connections metric if available
        try:
            ms = getattr(websocket.app.state, 'metrics_service', None)
            if ms and getattr(ms, 'websocket_connections', None):
                ms.websocket_connections.inc()
        except Exception:
            pass
        
        try:
            # Get services from app state
            metrics_service = getattr(websocket.app.state, 'metrics_service', None)
            adapter_manager = get_adapter_manager(websocket)
            thread_pool_manager = getattr(websocket.app.state, 'thread_pool_manager', None)
            
            # Helper to extract stats from a ThreadPoolExecutor
            def _stats_from_executor(executor) -> Dict[str, Any]:
                try:
                    max_workers = getattr(executor, '_max_workers', None)
                    threads = getattr(executor, '_threads', None)
                    work_q = getattr(executor, '_work_queue', None)
                    active_threads = len(threads) if threads is not None else 0
                    queued = work_q.qsize() if hasattr(work_q, 'qsize') else 0
                    return {
                        'max_workers': int(max_workers) if isinstance(max_workers, int) else 0,
                        'active_threads': int(active_threads),
                        'queued_tasks': int(queued),
                    }
                except Exception:
                    return {'max_workers': 0, 'active_threads': 0, 'queued_tasks': 0}

            while True:
                data: Dict[str, Any] = {}
                
                # Get metrics data
                if metrics_service:
                    data['metrics'] = metrics_service.get_dashboard_metrics()
                
                # Get adapter health status
                if adapter_manager:
                    try:
                        if hasattr(adapter_manager, 'get_health_status'):
                            health = adapter_manager.get_health_status()
                            adapters = health.get('circuit_breakers', {})
                            # Only include adapter data if we actually have adapters
                            if adapters:
                                data['adapters'] = adapters
                            else:
                                # Set empty adapters to trigger hiding the section
                                data['adapters'] = {}
                        elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                            # Try both methods for backward compatibility
                            if hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_status'):
                                adapters = adapter_manager.parallel_executor.get_circuit_breaker_status()
                                if adapters:
                                    data['adapters'] = adapters
                            elif hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_states'):
                                adapters = adapter_manager.parallel_executor.get_circuit_breaker_states()
                                if adapters:
                                    data['adapters'] = adapters
                        else:
                            data['adapters'] = {}
                    except Exception as e:
                        logger.debug(f"Error getting adapter status: {e}")
                        data['adapters'] = {}
                else:
                    # Set to empty if no adapter manager
                    data['adapters'] = {}
                
                # Get thread pool statistics
                # Always start with any central manager stats when available
                pools: Dict[str, Any] = {}
                if thread_pool_manager:
                    try:
                        pool_stats = thread_pool_manager.get_pool_stats()
                        # Only include pools that have been created (non-zero max_workers)
                        for pool_name, stats in pool_stats.items():
                            if stats.get('max_workers', 0) > 0:
                                pools[pool_name] = stats

                        # Push thread pool stats into Prometheus gauges if available
                        if metrics_service and hasattr(metrics_service, 'update_thread_pool_metrics'):
                            try:
                                metrics_service.update_thread_pool_metrics(pools)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Error getting thread pool stats: {e}")
                # Add service-specific executors if present (parallel executor, dynamic manager)
                try:
                    if adapter_manager:
                        # Parallel executor pool
                        pe = getattr(adapter_manager, 'parallel_executor', None)
                        if pe and hasattr(pe, 'thread_pool') and pe.thread_pool:
                            pools['parallel_executor'] = _stats_from_executor(pe.thread_pool)
                        # Dynamic adapter manager initialization pool
                        base_mgr = getattr(adapter_manager, 'base_adapter_manager', None)
                        if base_mgr and hasattr(base_mgr, '_thread_pool') and base_mgr._thread_pool:
                            pools['adapter_init'] = _stats_from_executor(base_mgr._thread_pool)
                except Exception as e:
                    logger.debug(f"Error collecting service executor stats: {e}")
                if pools:
                    data['thread_pools'] = pools

                # Get datasource pool statistics
                try:
                    from datasources.registry import get_registry as get_datasource_registry
                    datasource_registry = get_datasource_registry()
                    pool_stats = datasource_registry.get_pool_stats()
                    logger.debug(f"Datasource pool stats: {pool_stats}")
                    if pool_stats and pool_stats.get('total_cached_datasources', 0) > 0:
                        data['datasource_pool'] = pool_stats
                except Exception as e:
                    logger.warning(f"Error getting datasource pool stats: {e}")

                # Add server mode information for dashboard display
                data['server_mode'] = {
                    'adapters_available': bool(data.get('adapters'))
                }
                
                # Send data to client
                await websocket.send_json(data)
                
                # Wait before next update (use configured interval)
                metrics_service = getattr(websocket.app.state, 'metrics_service', None)
                update_interval = 5  # default
                if metrics_service:
                    update_interval = getattr(metrics_service, 'websocket_update_interval', 5)
                
                await asyncio.sleep(update_interval)
                
        except WebSocketDisconnect:
            active_connections.remove(websocket)
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if websocket in active_connections:
                active_connections.remove(websocket)
        finally:
            try:
                ms = getattr(websocket.app.state, 'metrics_service', None)
                if ms and getattr(ms, 'websocket_connections', None):
                    ms.websocket_connections.dec()
            except Exception:
                pass
    
    @router.get("/metrics")
    async def get_prometheus_metrics(metrics_service = Depends(get_metrics_service_for_prometheus)):
        """Prometheus metrics endpoint"""
        metrics_data = metrics_service.get_prometheus_metrics()
        return Response(content=metrics_data, media_type="text/plain")
    
    @router.get("/metrics/json")
    async def get_json_metrics(metrics_service = Depends(get_metrics_service_for_dashboard)):
        """JSON metrics endpoint for custom integrations"""
        return metrics_service.get_dashboard_metrics()
    
    return router
