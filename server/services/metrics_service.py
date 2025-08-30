"""
Metrics Service for Prometheus Integration

Provides centralized metrics collection and monitoring for the ORBIT server.
"""

import time
import os
import psutil
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import deque, defaultdict
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Summary,
    generate_latest,
    CollectorRegistry,
)
try:
    # Optional default collectors for richer metrics
    from prometheus_client import ProcessCollector, PlatformCollector, GCCollector
except Exception:  # pragma: no cover - optional depending on prometheus_client version
    ProcessCollector = PlatformCollector = GCCollector = None
try:
    from prometheus_client import multiprocess
except Exception:  # pragma: no cover
    multiprocess = None
import logging

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for collecting and exposing Prometheus metrics"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Get monitoring configuration with defaults
        monitoring_config = config.get('monitoring', {})
        self.enabled = monitoring_config.get('enabled', True)
        
        metrics_config = monitoring_config.get('metrics', {})
        self.collection_interval = metrics_config.get('collection_interval', 5)
        self.time_series_window = metrics_config.get('time_window', 300)  # 5 minutes default
        self.prometheus_enabled = metrics_config.get('prometheus', {}).get('enabled', True)
        
        dashboard_config = metrics_config.get('dashboard', {})
        self.dashboard_enabled = dashboard_config.get('enabled', True)
        self.websocket_update_interval = dashboard_config.get('websocket_update_interval', 5)
        
        # Alert thresholds (for future use)
        alerts_config = monitoring_config.get('alerts', {})
        self.cpu_threshold = alerts_config.get('cpu_threshold', 90)
        self.memory_threshold = alerts_config.get('memory_threshold', 85)
        self.error_rate_threshold = alerts_config.get('error_rate_threshold', 5)
        self.response_time_threshold = alerts_config.get('response_time_threshold', 5000)
        
        # Only initialize if monitoring is enabled
        if not self.enabled:
            logger.info("Metrics collection disabled by configuration")
            return
        
        # Get current process for process-specific metrics
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(interval=None)  # Initialize CPU measurement
            
        # Prepare registry with optional multiprocess support
        self.registry = CollectorRegistry()
        try:
            if multiprocess and os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
                multiprocess.MultiProcessCollector(self.registry)
            else:
                # Register default process/platform collectors when not using multiprocess
                if ProcessCollector:
                    ProcessCollector(registry=self.registry)
                if PlatformCollector:
                    PlatformCollector(registry=self.registry)
                if GCCollector:
                    GCCollector(registry=self.registry)
        except Exception as e:
            logger.debug(f"Prometheus default collectors setup skipped: {e}")
        
        # Request metrics
        self.request_counter = Counter(
            'orbit_http_requests_total',
            'Total number of HTTP requests',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )
        
        # Customize buckets if configured
        buckets = metrics_config.get('request_duration_buckets_seconds', None)
        self.request_duration = Histogram(
            'orbit_http_request_duration_seconds',
            'HTTP request latency',
            ['method', 'endpoint'],
            registry=self.registry,
            buckets=buckets if buckets else Histogram.DEFAULT_BUCKETS,
        )

        # In-flight requests
        self.http_inprogress = Gauge(
            'orbit_http_requests_in_progress',
            'In-progress HTTP requests',
            ['method', 'endpoint'],
            registry=self.registry,
        )
        
        # Adapter metrics
        self.adapter_requests = Counter(
            'orbit_adapter_requests_total',
            'Total adapter requests',
            ['adapter', 'status'],
            registry=self.registry
        )
        
        self.adapter_latency = Histogram(
            'orbit_adapter_latency_seconds',
            'Adapter response latency',
            ['adapter'],
            registry=self.registry
        )
        
        self.adapter_circuit_state = Gauge(
            'orbit_adapter_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=open, 2=half-open)',
            ['adapter'],
            registry=self.registry
        )
        
        # System metrics
        self.cpu_usage = Gauge(
            'orbit_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        self.memory_usage = Gauge(
            'orbit_memory_usage_mb',
            'Memory usage in MB',
            registry=self.registry,
        )
        
        self.thread_pool_active = Gauge(
            'orbit_thread_pool_active_threads',
            'Active threads in thread pool',
            ['pool'],
            registry=self.registry
        )
        
        self.thread_pool_queued = Gauge(
            'orbit_thread_pool_queued_tasks',
            'Queued tasks in thread pool',
            ['pool'],
            registry=self.registry
        )
        
        # WebSocket connections
        self.websocket_connections = Gauge(
            'orbit_websocket_connections',
            'Active WebSocket connections',
            registry=self.registry
        )
        
        # Authentication metrics
        self.auth_attempts = Counter(
            'orbit_auth_attempts_total',
            'Authentication attempts',
            ['result'],
            registry=self.registry
        )
        
        self.active_sessions = Gauge(
            'orbit_active_sessions',
            'Active user sessions',
            registry=self.registry
        )
        
        # API Key metrics
        self.api_key_usage = Counter(
            'orbit_api_key_usage_total',
            'API key usage',
            ['key_id'],
            registry=self.registry
        )
        
        # Health check metrics
        self.health_check_status = Gauge(
            'orbit_health_check_status',
            'Health check status (1=healthy, 0=unhealthy)',
            ['component'],
            registry=self.registry
        )
        
        # Time series data for dashboard - use configured values
        max_data_points = self.time_series_window // self.collection_interval
        self.time_series_data = {
            'cpu': deque(maxlen=max_data_points),
            'memory': deque(maxlen=max_data_points),
            'requests_per_second': deque(maxlen=max_data_points),
            'error_rate': deque(maxlen=max_data_points),
            'response_time': deque(maxlen=max_data_points),
            'timestamps': deque(maxlen=max_data_points)
        }
        
        # Request tracking for rate calculations
        self.request_timestamps = deque(maxlen=1000)
        self.error_timestamps = deque(maxlen=1000)
        self.response_times = deque(maxlen=100)
        
        # Start background metrics collection
        self._collection_task = None
        self._start_time = time.time()
    
    async def start_collection(self):
        """Start background metrics collection"""
        if not self.enabled:
            logger.info("Metrics collection disabled - skipping background task")
            return
            
        if not self._collection_task:
            self._collection_task = asyncio.create_task(self._collect_system_metrics())
            logger.info(f"Started metrics collection task (interval: {self.collection_interval}s)")
    
    async def stop_collection(self):
        """Stop background metrics collection"""
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped metrics collection task")
    
    async def _collect_system_metrics(self):
        """Continuously collect system metrics"""
        while True:
            try:
                # Collect CPU and memory for the current process
                cpu_percent = self.process.cpu_percent(interval=None)
                memory_info = self.process.memory_info()
                memory_mb = round(memory_info.rss / (1024 * 1024), 2)

                # Update gauges
                self.cpu_usage.set(cpu_percent)
                self.memory_usage.set(memory_mb)

                # Calculate request rate
                now = time.time()
                cutoff = now - 60  # Last minute
                recent_requests = [t for t in self.request_timestamps if t > cutoff]
                requests_per_second = len(recent_requests) / 60.0 if recent_requests else 0

                # Calculate error rate
                recent_errors = [t for t in self.error_timestamps if t > cutoff]
                error_rate = (len(recent_errors) / len(recent_requests) * 100) if recent_requests else 0

                # Calculate average response time
                avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0

                # Store time series data
                timestamp = datetime.now().isoformat()
                self.time_series_data['cpu'].append(cpu_percent)
                
                # Calculate memory percentage relative to total system memory
                total_mem = psutil.virtual_memory().total
                memory_percent = (memory_info.rss / total_mem) * 100 if total_mem > 0 else 0
                self.time_series_data['memory'].append(memory_percent)

                self.time_series_data['requests_per_second'].append(requests_per_second)
                self.time_series_data['error_rate'].append(error_rate)
                self.time_series_data['response_time'].append(avg_response_time * 1000)  # Convert to ms
                self.time_series_data['timestamps'].append(timestamp)

                await asyncio.sleep(self.collection_interval)

            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
                await asyncio.sleep(self.collection_interval)
    
    def record_request(self, method: str, endpoint: str, status: int, duration: float):
        """Record HTTP request metrics"""
        if not self.enabled:
            return
            
        self.request_counter.labels(method=method, endpoint=endpoint, status=str(status)).inc()
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
        
        # Track for rate calculations
        now = time.time()
        self.request_timestamps.append(now)
        if status >= 400:
            self.error_timestamps.append(now)
        self.response_times.append(duration)
    
    def record_adapter_request(self, adapter: str, status: str, duration: float):
        """Record adapter request metrics"""
        if not self.enabled:
            return
        self.adapter_requests.labels(adapter=adapter, status=status).inc()
        self.adapter_latency.labels(adapter=adapter).observe(duration)
    
    def update_circuit_breaker_state(self, adapter: str, state: str):
        """Update circuit breaker state metric"""
        if not self.enabled:
            return
        state_map = {'closed': 0, 'open': 1, 'half-open': 2}
        self.adapter_circuit_state.labels(adapter=adapter).set(state_map.get(state, -1))
    
    def update_thread_pool_metrics(self, pool_stats: Dict[str, Any]):
        """Update thread pool metrics"""
        if not self.enabled:
            return
        for pool_name, stats in pool_stats.items():
            if isinstance(stats.get('active_threads'), int):
                self.thread_pool_active.labels(pool=pool_name).set(stats['active_threads'])
            if isinstance(stats.get('queued_tasks'), int):
                self.thread_pool_queued.labels(pool=pool_name).set(stats['queued_tasks'])
    
    def record_auth_attempt(self, success: bool):
        """Record authentication attempt"""
        if not self.enabled:
            return
        result = 'success' if success else 'failure'
        self.auth_attempts.labels(result=result).inc()
    
    def update_active_sessions(self, count: int):
        """Update active sessions count"""
        if not self.enabled:
            return
        self.active_sessions.set(count)
    
    def record_api_key_usage(self, key_id: str):
        """Record API key usage"""
        if not self.enabled:
            return
        self.api_key_usage.labels(key_id=key_id).inc()
    
    def update_health_status(self, component: str, healthy: bool):
        """Update health check status"""
        if not self.enabled:
            return
        self.health_check_status.labels(component=component).set(1 if healthy else 0)
    
    def is_enabled(self) -> bool:
        """Check if monitoring is enabled"""
        return self.enabled
    
    def is_prometheus_enabled(self) -> bool:
        """Check if Prometheus endpoint is enabled"""
        return self.enabled and self.prometheus_enabled
    
    def is_dashboard_enabled(self) -> bool:
        """Check if dashboard is enabled"""
        return self.enabled and self.dashboard_enabled
    
    def get_prometheus_metrics(self) -> bytes:
        """Get Prometheus metrics in text format"""
        if not self.is_prometheus_enabled():
            return b"# Prometheus metrics disabled\n"
        return generate_latest(self.registry)
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Get metrics formatted for dashboard display"""
        uptime_seconds = time.time() - self._start_time
        uptime_str = self._format_uptime(uptime_seconds)

        # Calculate current rates
        now = time.time()
        cutoff = now - 60
        recent_requests = [t for t in self.request_timestamps if t > cutoff]
        requests_per_second = len(recent_requests) / 60.0 if recent_requests else 0
        recent_errors = [t for t in self.error_timestamps if t > cutoff]
        error_rate = (len(recent_errors) / len(recent_requests) * 100) if recent_requests else 0

        # Process-specific metrics
        process_cpu_percent = self.process.cpu_percent(interval=None)
        process_memory_info = self.process.memory_info()
        process_memory_gb = round(process_memory_info.rss / (1024 * 1024 * 1024), 2)

        total_memory = psutil.virtual_memory()
        process_memory_percent = round((process_memory_info.rss / total_memory.total) * 100, 1) if total_memory.total > 0 else 0
        
        return {
            'system': {
                'cpu_percent': round(process_cpu_percent, 1),
                'memory_gb': process_memory_gb,
                'memory_percent': process_memory_percent,
                'disk_usage_percent': round(psutil.disk_usage('/').percent, 1),
                'uptime': uptime_str,
                'uptime_seconds': uptime_seconds
            },
            'requests': {
                'total': sum(1 for t in self.request_timestamps),
                'per_second': round(requests_per_second),  # Integer for requests per second
                'error_rate': round(error_rate, 2),
                'avg_response_time': round(sum(self.response_times) / len(self.response_times) * 1000, 2) if self.response_times else 0
            },
            'time_series': {
                'cpu': list(self.time_series_data['cpu']),
                'memory': list(self.time_series_data['memory']),
                'requests_per_second': list(self.time_series_data['requests_per_second']),
                'error_rate': list(self.time_series_data['error_rate']),
                'response_time': list(self.time_series_data['response_time']),
                'timestamps': list(self.time_series_data['timestamps'])
            }
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"
    
    async def close(self):
        """Clean up resources"""
        await self.stop_collection()