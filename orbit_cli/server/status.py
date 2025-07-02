"""Server status monitoring and metrics collection."""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import psutil

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ServerMetrics:
    """Collects and formats server metrics."""
    
    @staticmethod
    def collect_basic(process: psutil.Process) -> Dict[str, Any]:
        """
        Collect basic server metrics.
        
        Args:
            process: psutil Process object
            
        Returns:
            Dictionary of basic metrics
        """
        try:
            memory_info = process.memory_info()
            
            return {
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent(interval=0.1),
                "num_threads": process.num_threads(),
                "create_time": process.create_time()
            }
        except Exception as e:
            logger.error(f"Error collecting basic metrics: {e}")
            return {}
    
    @staticmethod
    def collect_detailed(process: psutil.Process) -> Dict[str, Any]:
        """
        Collect detailed server metrics.
        
        Args:
            process: psutil Process object
            
        Returns:
            Dictionary of detailed metrics
        """
        metrics = ServerMetrics.collect_basic(process)
        
        try:
            # Memory details
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            metrics.update({
                "memory_rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "memory_percent": round(memory_percent, 2),
            })
            
            # CPU details
            cpu_times = process.cpu_times()
            metrics.update({
                "cpu_user_time": round(cpu_times.user, 2),
                "cpu_system_time": round(cpu_times.system, 2),
            })
            
            # I/O counters (if available)
            try:
                io_counters = process.io_counters()
                metrics.update({
                    "io_read_mb": round(io_counters.read_bytes / 1024 / 1024, 2),
                    "io_write_mb": round(io_counters.write_bytes / 1024 / 1024, 2),
                    "io_read_count": io_counters.read_count,
                    "io_write_count": io_counters.write_count,
                })
            except (psutil.AccessDenied, AttributeError):
                logger.debug("I/O counters not available")
            
            # Network connections
            try:
                connections = process.connections()
                metrics["num_connections"] = len(connections)
                
                # Count by status
                status_counts = {}
                for conn in connections:
                    status = conn.status
                    status_counts[status] = status_counts.get(status, 0) + 1
                metrics["connection_status"] = status_counts
            except (psutil.AccessDenied, AttributeError):
                logger.debug("Network connections not available")
            
            # Open files
            try:
                open_files = process.open_files()
                metrics["num_open_files"] = len(open_files)
            except (psutil.AccessDenied, AttributeError):
                logger.debug("Open files not available")
            
        except Exception as e:
            logger.error(f"Error collecting detailed metrics: {e}")
        
        return metrics
    
    @staticmethod
    def format_uptime(seconds: float) -> str:
        """
        Format uptime in human-readable format.
        
        Args:
            seconds: Uptime in seconds
            
        Returns:
            Formatted uptime string
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        
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


class ServerStatus:
    """Tracks and formats server status information."""
    
    def __init__(self):
        """Initialize the server status tracker."""
        self._status_history: List[Dict[str, Any]] = []
        self._max_history = 100
    
    def get_running_status(self, pid: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get status for a running server.
        
        Args:
            pid: Process ID
            metrics: Server metrics
            
        Returns:
            Status dictionary
        """
        uptime_seconds = time.time() - metrics.get("create_time", time.time())
        uptime_str = ServerMetrics.format_uptime(uptime_seconds)
        
        status = {
            "status": "running",
            "pid": pid,
            "uptime": uptime_str,
            "uptime_seconds": uptime_seconds,
            "message": f"Server is running with PID {pid}",
            "timestamp": datetime.now().isoformat()
        }
        
        # Add metrics
        status.update(metrics)
        
        # Track history
        self._add_to_history(status)
        
        return status
    
    def get_stopped_status(self) -> Dict[str, Any]:
        """Get status for a stopped server."""
        return {
            "status": "stopped",
            "message": "Server is not running",
            "timestamp": datetime.now().isoformat()
        }
    
    def get_error_status(self, pid: int, error: str) -> Dict[str, Any]:
        """
        Get status when there's an error checking the server.
        
        Args:
            pid: Process ID
            error: Error message
            
        Returns:
            Status dictionary
        """
        return {
            "status": "unknown",
            "pid": pid,
            "error": error,
            "message": f"Error checking server status: {error}",
            "timestamp": datetime.now().isoformat()
        }
    
    def get_health_status(self, health_check_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format health check results.
        
        Args:
            health_check_result: Result from health check endpoint
            
        Returns:
            Formatted health status
        """
        if health_check_result.get("status") == "healthy":
            return {
                "health": "healthy",
                "message": "Server is responding to health checks",
                **health_check_result
            }
        else:
            return {
                "health": "unhealthy",
                "message": "Server health check failed",
                **health_check_result
            }
    
    def _add_to_history(self, status: Dict[str, Any]) -> None:
        """Add status to history, maintaining size limit."""
        self._status_history.append(status.copy())
        
        # Trim history if needed
        if len(self._status_history) > self._max_history:
            self._status_history = self._status_history[-self._max_history:]
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get status history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of historical status entries
        """
        if limit:
            return self._status_history[-limit:]
        return self._status_history.copy()
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary from recent history.
        
        Returns:
            Performance summary statistics
        """
        if not self._status_history:
            return {"message": "No performance data available"}
        
        # Get recent entries (last 10 or all if less)
        recent = self._status_history[-10:]
        
        # Calculate averages
        cpu_values = [s.get("cpu_percent", 0) for s in recent if "cpu_percent" in s]
        memory_values = [s.get("memory_mb", 0) for s in recent if "memory_mb" in s]
        
        summary = {
            "samples": len(recent),
            "period": f"{len(recent)} status checks"
        }
        
        if cpu_values:
            summary["avg_cpu_percent"] = round(sum(cpu_values) / len(cpu_values), 2)
            summary["max_cpu_percent"] = round(max(cpu_values), 2)
            summary["min_cpu_percent"] = round(min(cpu_values), 2)
        
        if memory_values:
            summary["avg_memory_mb"] = round(sum(memory_values) / len(memory_values), 2)
            summary["max_memory_mb"] = round(max(memory_values), 2)
            summary["min_memory_mb"] = round(min(memory_values), 2)
        
        return summary


class ServerMonitor:
    """Monitors server status continuously."""
    
    def __init__(self, controller, interval: float = 5.0):
        """
        Initialize the server monitor.
        
        Args:
            controller: ServerController instance
            interval: Monitoring interval in seconds
        """
        self.controller = controller
        self.interval = interval
        self._running = False
    
    def start(self, callback=None):
        """
        Start monitoring the server.
        
        Args:
            callback: Optional callback function called with status dict
        """
        self._running = True
        
        try:
            while self._running:
                status = self.controller.status(detailed=True)
                
                if callback:
                    callback(status)
                else:
                    self._default_callback(status)
                
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    def stop(self):
        """Stop monitoring."""
        self._running = False
    
    def _default_callback(self, status: Dict[str, Any]):
        """Default callback that prints status."""
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        console.clear()
        
        # Create status table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        
        # Add rows based on status
        if status["status"] == "running":
            table.add_row("Status", "[green]Running[/green]")
            table.add_row("PID", str(status.get("pid", "N/A")))
            table.add_row("Uptime", status.get("uptime", "N/A"))
            
            if "memory_mb" in status:
                memory_str = f"{status['memory_mb']} MB"
                if "memory_percent" in status:
                    memory_str += f" ({status['memory_percent']}%)"
                table.add_row("Memory", memory_str)
            
            if "cpu_percent" in status:
                table.add_row("CPU", f"{status['cpu_percent']}%")
            
            if "num_threads" in status:
                table.add_row("Threads", str(status["num_threads"]))
            
            if "num_connections" in status:
                table.add_row("Connections", str(status["num_connections"]))
            
            if "io_read_mb" in status and "io_write_mb" in status:
                table.add_row(
                    "I/O",
                    f"R: {status['io_read_mb']} MB, W: {status['io_write_mb']} MB"
                )
        else:
            table.add_row("Status", f"[red]{status['status'].title()}[/red]")
            if "message" in status:
                table.add_row("Message", status["message"])
        
        console.print(table)
        console.print(f"\n[dim]Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        console.print("[dim]Press Ctrl+C to stop monitoring[/dim]")