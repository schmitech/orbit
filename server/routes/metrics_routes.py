"""
Metrics Routes for Real-time Monitoring

Provides WebSocket streaming and Prometheus/JSON metrics endpoints.
Login/logout/export/dashboard UI routes have moved to admin_panel_routes.py.
"""

import asyncio
import logging
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from fastapi.responses import Response

from routes.auth_helpers import authenticate_websocket_admin

logger = logging.getLogger(__name__)


def get_metrics_service(request: Request):
    """Get metrics service from app state"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service:
        raise HTTPException(status_code=503, detail="Metrics service not available")
    if not metrics_service.is_enabled():
        raise HTTPException(status_code=503, detail="Monitoring is disabled")
    return metrics_service


def get_metrics_service_for_prometheus(request: Request):
    """Get metrics service for Prometheus endpoints"""
    metrics_service = getattr(request.app.state, 'metrics_service', None)
    if not metrics_service or not metrics_service.is_prometheus_enabled():
        raise HTTPException(status_code=503, detail="Prometheus metrics are disabled")
    return metrics_service


def get_adapter_manager(request_or_ws):
    """Get adapter manager from app state"""
    manager = getattr(request_or_ws.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request_or_ws.app.state, 'adapter_manager', None)
    return manager


def create_metrics_router() -> APIRouter:
    """Create metrics router with WebSocket and metrics endpoints"""

    router = APIRouter(tags=["metrics"])

    # Store active WebSocket connections
    active_connections: list[WebSocket] = []

    @router.websocket("/ws/metrics")
    async def websocket_metrics(websocket: WebSocket):
        """WebSocket endpoint for real-time metrics streaming"""
        if not await authenticate_websocket_admin(websocket):
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
                            data['adapters'] = adapters if adapters else {}
                        elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
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
                    data['adapters'] = {}

                # Get thread pool statistics
                pools: Dict[str, Any] = {}
                if thread_pool_manager:
                    try:
                        pool_stats = thread_pool_manager.get_pool_stats()
                        for pool_name, stats in pool_stats.items():
                            if stats.get('max_workers', 0) > 0:
                                pools[pool_name] = stats

                        if metrics_service and hasattr(metrics_service, 'update_thread_pool_metrics'):
                            try:
                                metrics_service.update_thread_pool_metrics(pools)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Error getting thread pool stats: {e}")
                # Add service-specific executors if present
                try:
                    if adapter_manager:
                        pe = getattr(adapter_manager, 'parallel_executor', None)
                        if pe and hasattr(pe, 'thread_pool') and pe.thread_pool:
                            pools['parallel_executor'] = _stats_from_executor(pe.thread_pool)
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
                    if pool_stats and pool_stats.get('total_cached_datasources', 0) > 0:
                        data['datasource_pool'] = pool_stats
                except Exception as e:
                    logger.warning(f"Error getting datasource pool stats: {e}")

                # Get Redis health and connection pool statistics
                try:
                    redis_service = getattr(websocket.app.state, 'redis_service', None)
                    if redis_service:
                        redis_data: Dict[str, Any] = {
                            'enabled': getattr(redis_service, 'enabled', False),
                            'initialized': getattr(redis_service, 'initialized', False),
                        }
                        cb = getattr(redis_service, '_circuit_breaker', None)
                        if cb:
                            redis_data['circuit_breaker'] = {
                                'state': getattr(cb, '_state', 'unknown'),
                                'failure_count': getattr(cb, '_failure_count', 0),
                                'max_failures': getattr(cb, '_max_failures', 5),
                            }
                        client = getattr(redis_service, 'client', None)
                        if client:
                            pool = getattr(client, 'connection_pool', None)
                            if pool:
                                redis_data['pool'] = {
                                    'max_connections': getattr(pool, 'max_connections', 0),
                                    'created_connections': getattr(pool, '_created_connections', 0),
                                    'available_connections': len(getattr(pool, '_available_connections', [])),
                                    'in_use_connections': len(getattr(pool, '_in_use_connections', [])),
                                }
                        data['redis_health'] = redis_data
                except Exception as e:
                    logger.debug(f"Error getting Redis health stats: {e}")

                # Pipeline step metrics
                try:
                    pipeline_monitor = getattr(websocket.app.state, 'pipeline_monitor', None)
                    if pipeline_monitor:
                        step_metrics = pipeline_monitor.get_all_step_metrics()
                        if step_metrics:
                            steps_data = {}
                            for step_name, sm in step_metrics.items():
                                min_time = sm.min_execution_time if sm.total_executions > 0 else 0.0
                                steps_data[step_name] = {
                                    'total_executions': sm.total_executions,
                                    'success_rate': round(sm.success_rate, 4),
                                    'avg_time_ms': round(sm.avg_execution_time * 1000, 1),
                                    'min_time_ms': round(min_time * 1000, 1),
                                    'max_time_ms': round(sm.max_execution_time * 1000, 1),
                                }
                            data['pipeline_steps'] = steps_data
                            pm = pipeline_monitor.get_pipeline_metrics()
                            data['pipeline_summary'] = {
                                'total_executions': pm.get('total_pipeline_executions', 0),
                                'success_rate': round(pm.get('pipeline_success_rate', 0.0), 4),
                                'avg_time_ms': round(pm.get('avg_response_time', 0.0) * 1000, 1),
                            }
                except Exception as e:
                    logger.debug(f"Error getting pipeline metrics: {e}")

                # Active connections info
                data['connections'] = {
                    'websocket_clients': len(active_connections),
                }
                try:
                    if metrics_service and getattr(metrics_service, 'active_sessions', None):
                        data['connections']['active_sessions'] = int(metrics_service.active_sessions._value.get())
                except Exception:
                    data['connections']['active_sessions'] = 0

                data['server_mode'] = {
                    'adapters_available': bool(data.get('adapters'))
                }

                await websocket.send_json(data)

                # Wait before next update (use configured interval)
                metrics_service = getattr(websocket.app.state, 'metrics_service', None)
                update_interval = 5
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
    async def get_prometheus_metrics(metrics_service=Depends(get_metrics_service_for_prometheus)):
        """Prometheus metrics endpoint"""
        metrics_data = metrics_service.get_prometheus_metrics()
        return Response(content=metrics_data, media_type="text/plain")

    @router.get("/metrics/json")
    async def get_json_metrics(metrics_service=Depends(get_metrics_service)):
        """JSON metrics endpoint for custom integrations"""
        return metrics_service.get_dashboard_metrics()

    return router
