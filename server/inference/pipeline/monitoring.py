"""
Pipeline Monitoring and Observability

This module provides monitoring capabilities for the pipeline architecture,
including metrics collection, health checks, and performance tracking.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)

@dataclass
class StepMetrics:
    """Metrics for a single pipeline step."""
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    min_execution_time: float = float('inf')
    max_execution_time: float = 0.0
    recent_execution_times: deque = field(default_factory=lambda: deque(maxlen=100))
    error_messages: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate the success rate."""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions
    
    def record_execution(self, execution_time: float, success: bool, error_message: Optional[str] = None):
        """Record an execution."""
        self.total_executions += 1
        self.total_execution_time += execution_time
        self.recent_execution_times.append(execution_time)
        
        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1
            if error_message:
                self.error_messages.append(error_message)
        
        # Update min/max times
        self.min_execution_time = min(self.min_execution_time, execution_time)
        self.max_execution_time = max(self.max_execution_time, execution_time)
        
        # Update average
        self.avg_execution_time = self.total_execution_time / self.total_executions


class PipelineMonitor:
    """
    Monitor for tracking pipeline performance and health.
    
    This class provides comprehensive monitoring capabilities including
    metrics collection, health checks, and performance tracking.
    """
    
    def __init__(self):
        """Initialize the pipeline monitor."""
        self.step_metrics: Dict[str, StepMetrics] = defaultdict(StepMetrics)
        self.pipeline_metrics: Dict[str, Any] = defaultdict(int)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
    
    def record_step_execution(
        self,
        step_name: str,
        execution_time: float,
        success: bool,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record execution metrics for a pipeline step.
        
        Args:
            step_name: Name of the step
            execution_time: Execution time in seconds
            success: Whether the step executed successfully
            error_message: Error message if execution failed
            metadata: Additional metadata
        """
        with self._lock:
            metrics = self.step_metrics[step_name]
            metrics.record_execution(execution_time, success, error_message)
            
            # Record pipeline-level metrics
            self.pipeline_metrics['total_executions'] += 1
            if success:
                self.pipeline_metrics['successful_executions'] += 1
            else:
                self.pipeline_metrics['failed_executions'] += 1
            
            logger.debug(f"Recorded execution for {step_name}: {execution_time:.3f}s, success={success}")
    
    def record_step_metrics(self, step_name: str, execution_time: float, 
                           success: bool, error_message: Optional[str] = None) -> None:
        """
        Alias for record_step_execution for backward compatibility.
        """
        self.record_step_execution(step_name, execution_time, success, error_message)
    
    def record_pipeline_metrics(self, execution_time: float, success: bool) -> None:
        """
        Record overall pipeline execution metrics.
        
        Args:
            execution_time: Total pipeline execution time in seconds
            success: Whether the pipeline executed successfully
        """
        with self._lock:
            self.pipeline_metrics['total_pipeline_executions'] = self.pipeline_metrics.get('total_pipeline_executions', 0) + 1
            self.pipeline_metrics['total_pipeline_time'] = self.pipeline_metrics.get('total_pipeline_time', 0.0) + execution_time
            
            if success:
                self.pipeline_metrics['successful_pipeline_executions'] = self.pipeline_metrics.get('successful_pipeline_executions', 0) + 1
            else:
                self.pipeline_metrics['failed_pipeline_executions'] = self.pipeline_metrics.get('failed_pipeline_executions', 0) + 1
    
    def get_step_metrics(self, step_name: str) -> Optional[StepMetrics]:
        """
        Get metrics for a specific step.
        
        Args:
            step_name: Name of the step
            
        Returns:
            Step metrics or None if not found
        """
        return self.step_metrics.get(step_name)
    
    def get_all_step_metrics(self) -> Dict[str, StepMetrics]:
        """
        Get metrics for all steps.
        
        Returns:
            Dictionary mapping step names to their metrics
        """
        return dict(self.step_metrics)
    
    def get_pipeline_metrics(self) -> Dict[str, Any]:
        """
        Get overall pipeline metrics.
        
        Returns:
            Dictionary containing pipeline-level metrics
        """
        # Step-level metrics
        total_executions = self.pipeline_metrics.get('total_executions', 0)
        successful_executions = self.pipeline_metrics.get('successful_executions', 0)
        
        # Pipeline-level metrics
        total_pipeline_executions = self.pipeline_metrics.get('total_pipeline_executions', 0)
        successful_pipeline_executions = self.pipeline_metrics.get('successful_pipeline_executions', 0)
        total_pipeline_time = self.pipeline_metrics.get('total_pipeline_time', 0.0)
        
        overall_success_rate = 0.0
        if total_executions > 0:
            overall_success_rate = successful_executions / total_executions
        
        pipeline_success_rate = 0.0
        if total_pipeline_executions > 0:
            pipeline_success_rate = successful_pipeline_executions / total_pipeline_executions
        
        avg_response_time = 0.0
        if total_pipeline_executions > 0:
            avg_response_time = total_pipeline_time / total_pipeline_executions
        elif self.step_metrics and total_executions > 0:
            total_time = sum(metrics.total_execution_time for metrics in self.step_metrics.values())
            avg_response_time = total_time / total_executions
        
        return {
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': self.pipeline_metrics.get('failed_executions', 0),
            'total_pipeline_executions': total_pipeline_executions,
            'successful_pipeline_executions': successful_pipeline_executions,
            'failed_pipeline_executions': self.pipeline_metrics.get('failed_pipeline_executions', 0),
            'overall_success_rate': overall_success_rate,
            'pipeline_success_rate': pipeline_success_rate,
            'avg_response_time': avg_response_time,
            'active_steps': len(self.step_metrics)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall system health status.
        
        Returns:
            Dictionary containing health information
        """
        pipeline_metrics = self.get_pipeline_metrics()
        
        # Determine health status - use pipeline success rate if available, otherwise overall
        success_rate = pipeline_metrics.get('pipeline_success_rate', 0.0)
        if success_rate == 0.0:
            success_rate = pipeline_metrics['overall_success_rate']
        if success_rate >= 0.95:
            status = "healthy"
        elif success_rate >= 0.80:
            status = "degraded"
        else:
            status = "unhealthy"
        
        # Check for recent errors
        recent_errors = []
        for step_name, metrics in self.step_metrics.items():
            if metrics.error_messages:
                recent_errors.append({
                    'step': step_name,
                    'errors': metrics.error_messages[-5:]  # Last 5 errors
                })
        
        return {
            'status': status,
            'pipeline_steps': list(self.step_metrics.keys()),
            'step_count': len(self.step_metrics),
            'monitoring': pipeline_metrics,
            'recent_errors': recent_errors
        }
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self.step_metrics.clear()
            self.pipeline_metrics.clear()
            logger.info("Reset all pipeline metrics")
    
    def export_metrics(self, format: str = "json") -> str:
        """
        Export metrics in the specified format.
        
        Args:
            format: Export format ("json" or "prometheus")
            
        Returns:
            Metrics in the specified format
        """
        if format == "json":
            return self._export_json_metrics()
        elif format == "prometheus":
            return self._export_prometheus_metrics()
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _export_json_metrics(self) -> str:
        """Export metrics as JSON."""
        import json
        
        metrics = {
            'pipeline': self.get_pipeline_metrics(),
            'steps': {}
        }
        
        for step_name, step_metrics in self.step_metrics.items():
            metrics['steps'][step_name] = {
                'total_executions': step_metrics.total_executions,
                'success_rate': step_metrics.success_rate,
                'avg_execution_time': step_metrics.avg_execution_time,
                'min_execution_time': step_metrics.min_execution_time,
                'max_execution_time': step_metrics.max_execution_time
            }
        
        return json.dumps(metrics, indent=2)
    
    def _export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        
        # Pipeline metrics
        pipeline_metrics = self.get_pipeline_metrics()
        lines.append("# HELP pipeline_executions_total Total pipeline executions")
        lines.append("# TYPE pipeline_executions_total counter")
        lines.append(f"pipeline_executions_total {pipeline_metrics['total_executions']}")
        
        lines.append("# HELP pipeline_success_rate Pipeline success rate")
        lines.append("# TYPE pipeline_success_rate gauge")
        lines.append(f"pipeline_success_rate {pipeline_metrics['overall_success_rate']}")
        
        # Step metrics
        for step_name, step_metrics in self.step_metrics.items():
            lines.append("# HELP pipeline_step_executions_total Total step executions")
            lines.append("# TYPE pipeline_step_executions_total counter")
            lines.append(f'pipeline_step_executions_total{{step="{step_name}"}} {step_metrics.total_executions}')
            
            lines.append("# HELP pipeline_step_success_rate Step success rate")
            lines.append("# TYPE pipeline_step_success_rate gauge")
            lines.append(f'pipeline_step_success_rate{{step="{step_name}"}} {step_metrics.success_rate}')
            
            lines.append("# HELP pipeline_step_execution_time_seconds Step execution time")
            lines.append("# TYPE pipeline_step_execution_time_seconds histogram")
            lines.append(f'pipeline_step_execution_time_seconds{{step="{step_name}"}} {step_metrics.avg_execution_time}')
        
        return "\n".join(lines) 