"""
Dashboard Routes for Real-time Monitoring

Provides web-based dashboard and metrics endpoints.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
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


def create_dashboard_router() -> APIRouter:
    """Create dashboard router with monitoring endpoints"""
    
    router = APIRouter(tags=["dashboard"])
    
    # Store active WebSocket connections
    active_connections: list[WebSocket] = []
    
    @router.get("/dashboard", response_class=HTMLResponse)
    async def get_dashboard(metrics_service = Depends(get_metrics_service_for_dashboard)):
        """Serve the monitoring dashboard"""
        dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORBIT Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .chart-container {
            position: relative;
            height: 250px;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        .pulse {
            animation: pulse 2s infinite;
        }
    </style>
</head>
<body class="bg-gray-900 text-white">
    <div class="container mx-auto p-6">
        <!-- Header -->
        <div class="mb-8">
            <h1 class="text-4xl font-bold mb-2">ORBIT Monitoring Dashboard</h1>
            <div class="flex items-center gap-4">
                <span id="connection-status" class="flex items-center">
                    <span id="status-indicator" class="w-3 h-3 bg-green-500 rounded-full mr-2 pulse"></span>
                    <span id="status-text">Connected</span>
                </span>
                <span class="text-gray-400">Last Updated: <span id="last-update">Never</span></span>
            </div>
        </div>

        <!-- Metrics Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <!-- CPU Usage -->
            <div class="metric-card rounded-lg p-6 text-white">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-sm opacity-75">CPU Usage</p>
                        <p class="text-3xl font-bold mt-2"><span id="cpu-usage">0</span>%</p>
                    </div>
                    <svg class="w-8 h-8 opacity-75" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
                    </svg>
                </div>
            </div>

            <!-- Memory Usage -->
            <div class="metric-card rounded-lg p-6 text-white">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-sm opacity-75">Memory Usage</p>
                        <p class="text-3xl font-bold mt-2"><span id="memory-usage">0</span> GB</p>
                        <p class="text-xs opacity-75 mt-1"><span id="memory-percent">0</span>%</p>
                    </div>
                    <svg class="w-8 h-8 opacity-75" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v1a1 1 0 001 1h4a1 1 0 001-1v-1m3-2V10a2 2 0 00-2-2H8a2 2 0 00-2 2v5m3-2h6"></path>
                    </svg>
                </div>
            </div>

            <!-- Requests/sec -->
            <div class="metric-card rounded-lg p-6 text-white">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-sm opacity-75">Requests/sec</p>
                        <p class="text-3xl font-bold mt-2"><span id="requests-per-second">0</span></p>
                        <p class="text-xs opacity-75 mt-1">Total: <span id="total-requests">0</span></p>
                    </div>
                    <svg class="w-8 h-8 opacity-75" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                    </svg>
                </div>
            </div>

            <!-- Error Rate -->
            <div class="metric-card rounded-lg p-6 text-white">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="text-sm opacity-75">Error Rate</p>
                        <p class="text-3xl font-bold mt-2"><span id="error-rate">0</span>%</p>
                        <p class="text-xs opacity-75 mt-1">Uptime: <span id="uptime">0m</span></p>
                    </div>
                    <svg class="w-8 h-8 opacity-75" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div id="charts-grid" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- CPU & Memory Chart -->
            <div class="bg-gray-800 rounded-lg p-6">
                <h2 class="text-xl font-semibold mb-4">System Resources</h2>
                <div class="chart-container">
                    <canvas id="system-chart"></canvas>
                </div>
            </div>

            <!-- Request Rate Chart -->
            <div class="bg-gray-800 rounded-lg p-6">
                <h2 class="text-xl font-semibold mb-4">Request Metrics</h2>
                <div class="chart-container">
                    <canvas id="request-chart"></canvas>
                </div>
            </div>

            <!-- Response Time Chart -->
            <div class="bg-gray-800 rounded-lg p-6">
                <h2 class="text-xl font-semibold mb-4">Response Time (ms)</h2>
                <div class="chart-container">
                    <canvas id="response-chart"></canvas>
                </div>
            </div>

            <!-- Adapter Status (conditionally shown) -->
            <div id="adapter-status-container" class="bg-gray-800 rounded-lg p-6" style="display: none;">
                <h2 class="text-xl font-semibold mb-4">Adapter Health</h2>
                <div id="adapter-status" class="space-y-2">
                    <p class="text-gray-400">Loading adapter status...</p>
                </div>
            </div>
        </div>

        <!-- Thread Pools Status -->
        <div class="mt-6 bg-gray-800 rounded-lg p-6">
            <h2 class="text-xl font-semibold mb-4">Thread Pool Status</h2>
            <div id="thread-pools" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <p class="text-gray-400">Loading thread pool status...</p>
            </div>
        </div>
    </div>

    <script>
        // WebSocket connection
        let ws = null;
        let reconnectInterval = null;
        
        // Chart configurations
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: 'rgba(255, 255, 255, 0.7)' }
                },
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    ticks: { color: 'rgba(255, 255, 255, 0.7)', maxRotation: 0, minRotation: 0 }
                }
            },
            plugins: {
                legend: {
                    labels: { color: 'rgba(255, 255, 255, 0.9)' }
                }
            }
        };

        // Initialize charts
        const systemChart = new Chart(document.getElementById('system-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'CPU %',
                    data: [],
                    borderColor: 'rgb(59, 130, 246)',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.1
                }, {
                    label: 'Memory %',
                    data: [],
                    borderColor: 'rgb(16, 185, 129)',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.1
                }]
            },
            options: chartOptions
        });

        const requestChartOptions = {
            ...chartOptions,
            scales: {
                ...chartOptions.scales,
                y: {
                    ...chartOptions.scales.y,
                    ticks: { 
                        ...chartOptions.scales.y.ticks,
                        stepSize: 1,  // Force integer steps
                        precision: 0   // Force integer precision
                    },
                    min: 0  // Ensure 0 is always shown
                }
            },
            plugins: {
                ...chartOptions.plugins,
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.datasetIndex === 0) {
                                // Requests/sec - show as integer
                                label += Math.round(context.parsed.y);
                            } else {
                                // Error Rate % - show with 2 decimals
                                label += context.parsed.y.toFixed(2) + '%';
                            }
                            return label;
                        }
                    }
                }
            }
        };

        const requestChart = new Chart(document.getElementById('request-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Requests/sec',
                    data: [],
                    borderColor: 'rgb(251, 191, 36)',
                    backgroundColor: 'rgba(251, 191, 36, 0.1)',
                    tension: 0.1
                }, {
                    label: 'Error Rate %',
                    data: [],
                    borderColor: 'rgb(239, 68, 68)',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.1
                }]
            },
            options: requestChartOptions
        });

        const responseChart = new Chart(document.getElementById('response-chart'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Avg Response Time',
                    data: [],
                    borderColor: 'rgb(139, 92, 246)',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    tension: 0.1
                }]
            },
            options: chartOptions
        });

        function updateMetrics(data) {
            // Update metric cards
            document.getElementById('cpu-usage').textContent = data.system.cpu_percent.toFixed(1);
            document.getElementById('memory-usage').textContent = data.system.memory_gb;
            document.getElementById('memory-percent').textContent = data.system.memory_percent.toFixed(1);
            document.getElementById('requests-per-second').textContent = data.requests.per_second;
            document.getElementById('total-requests').textContent = data.requests.total;
            document.getElementById('error-rate').textContent = data.requests.error_rate.toFixed(2);
            document.getElementById('uptime').textContent = data.system.uptime;

            // Update last update time
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

            // Update charts with time series data
            if (data.time_series && data.time_series.timestamps.length > 0) {
                const labels = data.time_series.timestamps.map(t => 
                    new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                );
                const maxPoints = 30;
                const startIdx = Math.max(0, labels.length - maxPoints);

                // Update system chart
                systemChart.data.labels = labels.slice(startIdx);
                systemChart.data.datasets[0].data = data.time_series.cpu.slice(startIdx);
                systemChart.data.datasets[1].data = data.time_series.memory.slice(startIdx);
                systemChart.update('none');

                // Update request chart
                requestChart.data.labels = labels.slice(startIdx);
                requestChart.data.datasets[0].data = data.time_series.requests_per_second.slice(startIdx);
                requestChart.data.datasets[1].data = data.time_series.error_rate.slice(startIdx);
                requestChart.update('none');

                // Update response chart
                responseChart.data.labels = labels.slice(startIdx);
                responseChart.data.datasets[0].data = data.time_series.response_time.slice(startIdx);
                responseChart.update('none');
            }
        }

        function updateAdapterStatus(data) {
            const container = document.getElementById('adapter-status');
            const containerDiv = document.getElementById('adapter-status-container');
            const chartsGrid = document.getElementById('charts-grid');
            
            if (data.adapters && Object.keys(data.adapters).length > 0) {
                // Show the adapter section if we have adapters
                containerDiv.style.display = 'block';
                // Keep the normal 2x2 grid layout
                chartsGrid.className = 'grid grid-cols-1 lg:grid-cols-2 gap-6';
                
                const html = Object.entries(data.adapters).map(([name, status]) => {
                    const stateColor = status.state === 'closed' ? 'bg-green-500' : 
                                      status.state === 'open' ? 'bg-red-500' : 'bg-yellow-500';
                    return `
                        <div class="flex items-center justify-between p-2 bg-gray-700 rounded">
                            <span class="font-medium">${name}</span>
                            <div class="flex items-center gap-2">
                                <span class="text-sm text-gray-400">
                                    ${status.failure_count || 0} failures
                                </span>
                                <span class="px-2 py-1 text-xs rounded ${stateColor} text-white">
                                    ${status.state}
                                </span>
                            </div>
                        </div>
                    `;
                }).join('');
                container.innerHTML = html;
            } else {
                // Hide the adapter section if no adapters are configured
                containerDiv.style.display = 'none';
                // Expand the remaining charts to fill the space better
                chartsGrid.className = 'grid grid-cols-1 lg:grid-cols-3 gap-6';
            }
        }

        function updateThreadPools(data) {
            const container = document.getElementById('thread-pools');
            if (data.pools && Object.keys(data.pools).length > 0) {
                const html = Object.entries(data.pools).map(([name, pool]) => {
                    const utilization = pool.max_workers > 0 ? 
                        ((pool.active_threads / pool.max_workers) * 100).toFixed(1) : 0;
                    return `
                        <div class="bg-gray-700 rounded p-4">
                            <h3 class="font-medium mb-2">${name}</h3>
                            <div class="space-y-1 text-sm">
                                <p>Active: ${pool.active_threads} / ${pool.max_workers}</p>
                                <p>Queued: ${pool.queued_tasks}</p>
                                <p>Utilization: ${utilization}%</p>
                            </div>
                        </div>
                    `;
                }).join('');
                container.innerHTML = html;
            } else {
                container.innerHTML = '<p class="text-gray-400">No thread pool data available</p>';
            }
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/metrics`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('status-indicator').className = 'w-3 h-3 bg-green-500 rounded-full mr-2 pulse';
                document.getElementById('status-text').textContent = 'Connected';
                clearInterval(reconnectInterval);
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateMetrics(data.metrics);
                
                // Handle adapter status with server mode awareness
                if (data.server_mode && data.server_mode.inference_only) {
                    // Hide adapter section in inference-only mode
                    document.getElementById('adapter-status-container').style.display = 'none';
                    document.getElementById('charts-grid').className = 'grid grid-cols-1 lg:grid-cols-3 gap-6';
                } else if (data.adapters) {
                    updateAdapterStatus({adapters: data.adapters});
                } else {
                    // No adapters available (not inference-only mode but no adapters configured)
                    updateAdapterStatus({adapters: {}});
                }
                
                if (data.thread_pools) {
                    updateThreadPools(data.thread_pools);
                }
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('status-indicator').className = 'w-3 h-3 bg-red-500 rounded-full mr-2';
                document.getElementById('status-text').textContent = 'Disconnected';
                
                // Attempt to reconnect
                clearInterval(reconnectInterval);
                reconnectInterval = setInterval(() => {
                    console.log('Attempting to reconnect...');
                    connectWebSocket();
                }, 5000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        // Connect on page load
        connectWebSocket();
        
        // Clean up on page unload
        window.addEventListener('beforeunload', () => {
            if (ws) {
                ws.close();
            }
            clearInterval(reconnectInterval);
        });
    </script>
</body>
</html>
        """
        return dashboard_html
    
    @router.websocket("/ws/metrics")
    async def websocket_metrics(websocket: WebSocket):
        """WebSocket endpoint for real-time metrics streaming"""
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
                
                # Get adapter health status - only if not in inference_only mode
                config = getattr(websocket.app.state, 'config', {})
                inference_only = config.get('general', {}).get('inference_only', False)
                
                if not inference_only and adapter_manager:
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
                    # Explicitly set to empty if in inference_only mode or no adapter manager
                    data['adapters'] = {}
                
                # Get thread pool statistics
                # Always start with any central manager stats when available
                pools: Dict[str, Any] = {}
                if thread_pool_manager:
                    try:
                        pools.update(thread_pool_manager.get_pool_stats())
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
                
                # Add server mode information for dashboard display
                data['server_mode'] = {
                    'inference_only': inference_only,
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
            logger.info("WebSocket client disconnected")
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
