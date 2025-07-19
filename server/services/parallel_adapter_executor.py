"""
Simplified Parallel Adapter Executor with Circuit Breaker Protection

This module provides a streamlined approach to executing multiple adapters
in parallel with circuit breaker protection and timeout handling.
"""

import asyncio
import time
import logging
import random
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import functools
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerStats:
    """Simple stats for circuit breaker with memory leak prevention"""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    timeout_calls: int = 0
    
    # Time-series data for memory leak prevention
    call_history: List[Dict[str, Any]] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_call_record(self, timestamp: float, success: bool, execution_time: float = 0.0):
        """Add a call record to history"""
        self.call_history.append({
            'timestamp': timestamp,
            'success': success,
            'execution_time': execution_time
        })
    
    def add_state_transition(self, timestamp: float, from_state: str, to_state: str, reason: str = ""):
        """Add a state transition record"""
        self.state_transitions.append({
            'timestamp': timestamp,
            'from_state': from_state,
            'to_state': to_state,
            'reason': reason
        })
    
    def cleanup_old_records(self, cutoff_time: float):
        """Remove records older than cutoff_time"""
        # Clean up call history
        self.call_history = [
            record for record in self.call_history 
            if record['timestamp'] >= cutoff_time
        ]
        
        # Clean up state transitions
        self.state_transitions = [
            transition for transition in self.state_transitions 
            if transition['timestamp'] >= cutoff_time
        ]

@dataclass
class AdapterExecutionContext:
    """Context to propagate through adapter execution"""
    request_id: str
    user_id: Optional[str] = None
    api_key: Optional[str] = None
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def get_log_prefix(self) -> str:
        """Get a consistent log prefix for this context"""
        parts = [f"[{self.request_id}]"]
        if self.trace_id:
            parts.append(f"trace:{self.trace_id}")
        if self.user_id:
            parts.append(f"user:{self.user_id}")
        if self.session_id:
            parts.append(f"session:{self.session_id}")
        return " ".join(parts)

@dataclass
class AdapterResult:
    """Result from adapter execution"""
    adapter_name: str
    success: bool
    data: Any = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    context: Optional[AdapterExecutionContext] = None


class CircuitBreakerEventHandler(ABC):
    """Abstract base class for circuit breaker event handlers"""
    
    @abstractmethod
    async def on_circuit_open(self, adapter_name: str, stats: Dict[str, Any], reason: str = ""):
        """Called when circuit opens"""
        pass
    
    @abstractmethod
    async def on_circuit_close(self, adapter_name: str, stats: Dict[str, Any]):
        """Called when circuit closes"""
        pass
    
    @abstractmethod
    async def on_circuit_half_open(self, adapter_name: str, stats: Dict[str, Any]):
        """Called when circuit transitions to half-open"""
        pass
    
    @abstractmethod
    async def on_circuit_reset(self, adapter_name: str, stats: Dict[str, Any]):
        """Called when circuit is reset"""
        pass


class DefaultCircuitBreakerEventHandler(CircuitBreakerEventHandler):
    """Default event handler that logs events"""
    
    async def on_circuit_open(self, adapter_name: str, stats: Dict[str, Any], reason: str = ""):
        """Log circuit open event"""
        logger.warning(f"Circuit breaker OPENED for adapter: {adapter_name} - {reason}")
    
    async def on_circuit_close(self, adapter_name: str, stats: Dict[str, Any]):
        """Log circuit close event"""
        logger.info(f"Circuit breaker CLOSED for adapter: {adapter_name}")
    
    async def on_circuit_half_open(self, adapter_name: str, stats: Dict[str, Any]):
        """Log circuit half-open event"""
        logger.info(f"Circuit breaker HALF-OPEN for adapter: {adapter_name}")
    
    async def on_circuit_reset(self, adapter_name: str, stats: Dict[str, Any]):
        """Log circuit reset event"""
        logger.info(f"Circuit breaker RESET for adapter: {adapter_name}")


class MonitoringCircuitBreakerEventHandler(CircuitBreakerEventHandler):
    """Event handler for monitoring systems with alerting capabilities"""
    
    def __init__(self, alert_callback: Optional[Callable] = None, 
                 dashboard_callback: Optional[Callable] = None,
                 metrics_callback: Optional[Callable] = None):
        self.alert_callback = alert_callback
        self.dashboard_callback = dashboard_callback
        self.metrics_callback = metrics_callback
    
    async def on_circuit_open(self, adapter_name: str, stats: Dict[str, Any], reason: str = ""):
        """Handle circuit open with monitoring integration"""
        # Log the event
        logger.warning(f"Circuit breaker OPENED for adapter: {adapter_name} - {reason}")
        
        # Send alert if callback provided
        if self.alert_callback:
            try:
                await self.alert_callback(
                    event_type="circuit_open",
                    adapter_name=adapter_name,
                    stats=stats,
                    reason=reason
                )
            except Exception as e:
                logger.error(f"Failed to send alert for {adapter_name}: {e}")
        
        # Update dashboard if callback provided
        if self.dashboard_callback:
            try:
                await self.dashboard_callback(
                    event_type="circuit_open",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update dashboard for {adapter_name}: {e}")
        
        # Update metrics if callback provided
        if self.metrics_callback:
            try:
                await self.metrics_callback(
                    event_type="circuit_open",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update metrics for {adapter_name}: {e}")
    
    async def on_circuit_close(self, adapter_name: str, stats: Dict[str, Any]):
        """Handle circuit close with monitoring integration"""
        # Log the event
        logger.info(f"Circuit breaker CLOSED for adapter: {adapter_name}")
        
        # Update dashboard if callback provided
        if self.dashboard_callback:
            try:
                await self.dashboard_callback(
                    event_type="circuit_close",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update dashboard for {adapter_name}: {e}")
        
        # Update metrics if callback provided
        if self.metrics_callback:
            try:
                await self.metrics_callback(
                    event_type="circuit_close",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update metrics for {adapter_name}: {e}")
    
    async def on_circuit_half_open(self, adapter_name: str, stats: Dict[str, Any]):
        """Handle circuit half-open with monitoring integration"""
        # Log the event
        logger.info(f"Circuit breaker HALF-OPEN for adapter: {adapter_name}")
        
        # Update dashboard if callback provided
        if self.dashboard_callback:
            try:
                await self.dashboard_callback(
                    event_type="circuit_half_open",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update dashboard for {adapter_name}: {e}")
    
    async def on_circuit_reset(self, adapter_name: str, stats: Dict[str, Any]):
        """Handle circuit reset with monitoring integration"""
        # Log the event
        logger.info(f"Circuit breaker RESET for adapter: {adapter_name}")
        
        # Update dashboard if callback provided
        if self.dashboard_callback:
            try:
                await self.dashboard_callback(
                    event_type="circuit_reset",
                    adapter_name=adapter_name,
                    stats=stats
                )
            except Exception as e:
                logger.error(f"Failed to update dashboard for {adapter_name}: {e}")
    
class SimpleCircuitBreaker:
    """Simplified circuit breaker for a single adapter"""
    
    def __init__(self, adapter_name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, success_threshold: int = 3,
                 max_recovery_timeout: float = 300.0, enable_exponential_backoff: bool = True,
                 cleanup_interval: float = 3600.0, retention_period: float = 86400.0,
                 event_handler: Optional[CircuitBreakerEventHandler] = None):
        self.adapter_name = adapter_name
        self.failure_threshold = failure_threshold
        self.base_recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.max_recovery_timeout = max_recovery_timeout
        self.enable_exponential_backoff = enable_exponential_backoff
        
        # Memory leak prevention settings
        self.cleanup_interval = cleanup_interval  # How often to run cleanup (default: 1 hour)
        self.retention_period = retention_period  # How long to keep data (default: 24 hours)
        self._last_cleanup = time.time()
        
        # Event handling
        self.event_handler = event_handler or DefaultCircuitBreakerEventHandler()
        
        # Exponential backoff tracking
        self.recovery_attempts = 0
        self.current_recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
    
    def _calculate_recovery_timeout(self) -> float:
        """Calculate recovery timeout with exponential backoff and jitter"""
        if not self.enable_exponential_backoff:
            return self.base_recovery_timeout
        
        # Exponential backoff with jitter
        backoff = min(
            self.base_recovery_timeout * (2 ** self.recovery_attempts),
            self.max_recovery_timeout
        )
        # Add jitter to prevent thundering herd (0-10% of backoff)
        jitter = random.uniform(0, backoff * 0.1)
        return backoff + jitter
    
    def is_open(self) -> bool:
        """Check if circuit is open"""
        if self.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if time.time() - self._state_changed_at >= self.current_recovery_timeout:
                self._transition_to_half_open()
                return False
            return True
        return False
    
    def can_execute(self) -> bool:
        """Check if the circuit allows execution (not open)"""
        return not self.is_open()
    
    def record_success(self, *args, **kwargs):
        """Record a successful call (accepts optional args for compatibility)"""
        current_time = time.time()
        
        # Add to call history
        execution_time = kwargs.get('execution_time', 0.0)
        self.stats.add_call_record(current_time, True, execution_time)
        
        # Update counters
        self.stats.success_count += 1
        self.stats.total_successes += 1
        self.stats.total_calls += 1
        self.stats.consecutive_successes += 1
        self.stats.consecutive_failures = 0
        self.stats.last_success_time = current_time
        
        # Check for cleanup
        self._maybe_cleanup_old_stats()
        
        if self.state == CircuitState.HALF_OPEN:
            if self.stats.consecutive_successes >= self.success_threshold:
                self._close_circuit()
        elif self.state == CircuitState.OPEN:
            # If a success occurs in OPEN (shouldn't happen), transition to HALF_OPEN
            self._transition_to_half_open()
    
    def record_failure(self, *args, **kwargs):
        """Record a failed call (accepts optional args for compatibility)"""
        current_time = time.time()
        
        # Add to call history
        execution_time = kwargs.get('execution_time', 0.0)
        self.stats.add_call_record(current_time, False, execution_time)
        
        # Update counters
        self.stats.failure_count += 1
        self.stats.total_failures += 1
        self.stats.total_calls += 1
        self.stats.consecutive_failures += 1
        self.stats.consecutive_successes = 0
        self.stats.last_failure_time = current_time
        
        # Check for cleanup
        self._maybe_cleanup_old_stats()
        
        if self.state == CircuitState.CLOSED:
            if self.stats.consecutive_failures >= self.failure_threshold:
                self._open_circuit()
        elif self.state == CircuitState.HALF_OPEN:
            self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit"""
        current_time = time.time()
        old_state = self.state.value
        
        self.state = CircuitState.OPEN
        self._state_changed_at = current_time
        
        # Record state transition
        self.stats.add_state_transition(current_time, old_state, "open", "failure_threshold_reached")
        
        # Increment recovery attempts for exponential backoff
        self.recovery_attempts += 1
        self.current_recovery_timeout = self._calculate_recovery_timeout()
        
        logger.warning(f"Circuit breaker OPENED for adapter: {self.adapter_name} "
                      f"(recovery_attempts={self.recovery_attempts}, "
                      f"next_timeout={self.current_recovery_timeout:.1f}s)")
        
        # Trigger event handler
        if self.event_handler:
            asyncio.create_task(
                self.event_handler.on_circuit_open(
                    self.adapter_name, 
                    self.get_status(), 
                    "failure_threshold_reached"
                )
            )
    
    def _close_circuit(self):
        """Close the circuit"""
        current_time = time.time()
        old_state = self.state.value
        
        self.state = CircuitState.CLOSED
        self._state_changed_at = current_time
        self.stats.consecutive_failures = 0
        self.stats.consecutive_successes = 0
        
        # Record state transition
        self.stats.add_state_transition(current_time, old_state, "closed", "success_threshold_reached")
        
        # Reset exponential backoff when circuit closes successfully
        self.recovery_attempts = 0
        self.current_recovery_timeout = self.base_recovery_timeout
        
        logger.info(f"Circuit breaker CLOSED for adapter: {self.adapter_name} "
                   f"(recovery_attempts reset to 0)")
        
        # Trigger event handler
        if self.event_handler:
            asyncio.create_task(
                self.event_handler.on_circuit_close(self.adapter_name, self.get_status())
            )
    
    def _transition_to_half_open(self):
        """Transition to half-open state"""
        current_time = time.time()
        old_state = self.state.value
        
        self.state = CircuitState.HALF_OPEN
        self._state_changed_at = current_time
        self.stats.consecutive_successes = 0
        
        # Record state transition
        self.stats.add_state_transition(current_time, old_state, "half_open", "recovery_timeout_expired")
        
        logger.info(f"Circuit breaker HALF-OPEN for adapter: {self.adapter_name}")
        
        # Trigger event handler
        if self.event_handler:
            asyncio.create_task(
                self.event_handler.on_circuit_half_open(self.adapter_name, self.get_status())
            )
    
    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status"""
        success_rate = 0.0
        if self.stats.total_calls > 0:
            success_rate = self.stats.total_successes / self.stats.total_calls
            
        return {
            "state": self.state.value,
            "success_rate": success_rate,
            "total_calls": self.stats.total_calls,
            "consecutive_failures": self.stats.consecutive_failures,
            "consecutive_successes": self.stats.consecutive_successes,
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time,
            "memory_usage": {
                "call_history_size": len(self.stats.call_history),
                "state_transitions_size": len(self.stats.state_transitions),
                "last_cleanup": self._last_cleanup,
                "cleanup_interval": self.cleanup_interval,
                "retention_period": self.retention_period
            },
            "exponential_backoff": {
                "enabled": self.enable_exponential_backoff,
                "recovery_attempts": self.recovery_attempts,
                "current_timeout": self.current_recovery_timeout,
                "base_timeout": self.base_recovery_timeout,
                "max_timeout": self.max_recovery_timeout
            }
        }
    
    def _maybe_cleanup_old_stats(self):
        """Periodically clean up old statistics to prevent memory leaks"""
        current_time = time.time()
        
        # Check if it's time for cleanup
        if current_time - self._last_cleanup > self.cleanup_interval:
            cutoff_time = current_time - self.retention_period
            
            # Get counts before cleanup
            call_history_before = len(self.stats.call_history)
            transitions_before = len(self.stats.state_transitions)
            
            # Perform cleanup
            self.stats.cleanup_old_records(cutoff_time)
            
            # Get counts after cleanup
            call_history_after = len(self.stats.call_history)
            transitions_after = len(self.stats.state_transitions)
            
            # Update last cleanup time
            self._last_cleanup = current_time
            
            # Log cleanup results if there was significant cleanup
            if call_history_before > call_history_after or transitions_before > transitions_after:
                logger.debug(f"Circuit breaker cleanup for {self.adapter_name}: "
                           f"removed {call_history_before - call_history_after} call records, "
                           f"{transitions_before - transitions_after} transition records")
    
    def force_cleanup(self):
        """Force immediate cleanup of old statistics"""
        current_time = time.time()
        cutoff_time = current_time - self.retention_period
        
        # Get counts before cleanup
        call_history_before = len(self.stats.call_history)
        transitions_before = len(self.stats.state_transitions)
        
        # Perform cleanup
        self.stats.cleanup_old_records(cutoff_time)
        
        # Get counts after cleanup
        call_history_after = len(self.stats.call_history)
        transitions_after = len(self.stats.state_transitions)
        
        # Update last cleanup time
        self._last_cleanup = current_time
        
        logger.info(f"Circuit breaker forced cleanup for {self.adapter_name}: "
                   f"removed {call_history_before - call_history_after} call records, "
                   f"{transitions_before - transitions_after} transition records")
    
    def reset(self):
        """Reset the circuit breaker stats and state"""
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
        
        # Reset exponential backoff state
        self.recovery_attempts = 0
        self.current_recovery_timeout = self.base_recovery_timeout
        
        # Reset cleanup tracking
        self._last_cleanup = time.time()
        
        logger.info(f"Circuit breaker RESET for adapter: {self.adapter_name} "
                   f"(exponential backoff reset)")
        
        # Trigger event handler
        if self.event_handler:
            asyncio.create_task(
                self.event_handler.on_circuit_reset(self.adapter_name, self.get_status())
            )

class ParallelAdapterExecutor:
    """
    Simplified parallel adapter executor with circuit breaker protection.
    
    This executor:
    - Runs adapters truly in parallel using asyncio
    - Applies circuit breaker pattern to each adapter
    - Handles timeouts properly
    - Provides simple, debuggable code
    """
    
    def __init__(self, adapter_manager, config: Dict[str, Any]):
        self.adapter_manager = adapter_manager
        self.config = config
        
        # Circuit breaker configuration
        ft_config = config.get('fault_tolerance', {})
        exec_config = ft_config.get('execution', {})
        self.failure_threshold = ft_config.get('failure_threshold', 5)
        self.recovery_timeout = ft_config.get('recovery_timeout', 60.0)
        self.success_threshold = ft_config.get('success_threshold', 3)
        # Use execution.timeout if available, else fallback
        self.operation_timeout = exec_config.get('timeout', ft_config.get('operation_timeout', 30.0))
        
        # Execution configuration
        self.max_concurrent = exec_config.get('max_concurrent_adapters', ft_config.get('max_concurrent_adapters', 10))
        self.execution_strategy = exec_config.get('strategy', ft_config.get('adapter_selection_strategy', 'all'))
        
        # Circuit breakers for each adapter
        self.circuit_breakers: Dict[str, SimpleCircuitBreaker] = {}
        
        # Thread pool for CPU-bound operations
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_concurrent)
        
        # Graceful shutdown handling
        self._shutdown_event = asyncio.Event()
        self._active_requests = set()
        self._shutdown_timeout = exec_config.get('shutdown_timeout', 30.0)
        
        logger.info(f"ParallelAdapterExecutor initialized with timeout={self.operation_timeout}s")
    
    @property
    def timeout(self):
        return self.operation_timeout
    
    @timeout.setter
    def timeout(self, value):
        self.operation_timeout = value
    
    @property
    def strategy(self):
        return self.execution_strategy
    
    @strategy.setter
    def strategy(self, value):
        self.execution_strategy = value
    
    def _combine_results(self, results: List[AdapterResult]) -> List[Dict[str, Any]]:
        """Combine successful adapter results into a single list with metadata."""
        combined = []
        for result in results:
            if result.success and result.data:
                for item in result.data:
                    item = dict(item)
                    item["adapter_name"] = result.adapter_name
                    item["execution_time"] = result.execution_time
                    
                    # Add context information if available
                    if result.context:
                        item["request_id"] = result.context.request_id
                        if result.context.trace_id:
                            item["trace_id"] = result.context.trace_id
                        if result.context.user_id:
                            item["user_id"] = result.context.user_id
                        if result.context.session_id:
                            item["session_id"] = result.context.session_id
                        if result.context.correlation_id:
                            item["correlation_id"] = result.context.correlation_id
                    
                    combined.append(item)
        return combined
    
    def get_circuit_breaker_states(self) -> Dict[str, Any]:
        """Get the state of all circuit breakers."""
        return {name: cb.get_status() for name, cb in self.circuit_breakers.items()}
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status of the executor."""
        total = len(self.circuit_breakers)
        healthy = sum(1 for cb in self.circuit_breakers.values() if cb.state == CircuitState.CLOSED)
        return {
            "total_adapters": total,
            "healthy_adapters": healthy,
            "circuit_breakers": self.get_circuit_breaker_states(),
            "adapter_configurations": self.get_adapter_configuration_info(),
            "shutdown_status": {
                "is_shutting_down": self.is_shutting_down(),
                "active_request_count": self.get_active_request_count(),
                "active_requests": self.get_active_requests(),
                "shutdown_timeout": self._shutdown_timeout
            }
        }
    
    def _get_adapter_config(self, adapter_name: str) -> Dict[str, Any]:
        """Get adapter-specific configuration"""
        adapter_configs = self.config.get('adapters', [])
        return next((a for a in adapter_configs if a['name'] == adapter_name), {})
    
    def _get_adapter_fault_tolerance_config(self, adapter_name: str) -> Dict[str, Any]:
        """Get adapter-specific fault tolerance configuration"""
        adapter_config = self._get_adapter_config(adapter_name)
        return adapter_config.get('fault_tolerance', {})
    
    def _get_circuit_breaker(self, adapter_name: str) -> SimpleCircuitBreaker:
        """Get or create circuit breaker for adapter with adapter-specific settings"""
        if adapter_name not in self.circuit_breakers:
            # Get adapter-specific fault tolerance config
            ft_config = self._get_adapter_fault_tolerance_config(adapter_name)
            
            # Use adapter-specific settings with fallback to global
            failure_threshold = ft_config.get('failure_threshold', self.failure_threshold)
            recovery_timeout = ft_config.get('recovery_timeout', self.recovery_timeout)
            success_threshold = ft_config.get('success_threshold', self.success_threshold)
            max_recovery_timeout = ft_config.get('max_recovery_timeout', 300.0)
            enable_exponential_backoff = ft_config.get('enable_exponential_backoff', True)
            
            logger.debug(f"Creating circuit breaker for {adapter_name} with "
                        f"failure_threshold={failure_threshold}, "
                        f"recovery_timeout={recovery_timeout}, "
                        f"success_threshold={success_threshold}, "
                        f"max_recovery_timeout={max_recovery_timeout}, "
                        f"exponential_backoff={enable_exponential_backoff}")
            
            # Get memory leak prevention settings
            cleanup_interval = ft_config.get('cleanup_interval', 3600.0)  # 1 hour default
            retention_period = ft_config.get('retention_period', 86400.0)  # 24 hours default
            
            # Get event handler configuration
            event_handler_config = ft_config.get('event_handler', {})
            event_handler = self._create_event_handler(event_handler_config)
            
            self.circuit_breakers[adapter_name] = SimpleCircuitBreaker(
                adapter_name,
                failure_threshold,
                recovery_timeout,
                success_threshold,
                max_recovery_timeout,
                enable_exponential_backoff,
                cleanup_interval,
                retention_period,
                event_handler
            )
        return self.circuit_breakers[adapter_name]
    
    def _create_event_handler(self, event_handler_config: Dict[str, Any]) -> Optional[CircuitBreakerEventHandler]:
        """Create event handler based on configuration"""
        if not event_handler_config:
            return None
        
        handler_type = event_handler_config.get('type', 'default')
        
        if handler_type == 'default':
            return DefaultCircuitBreakerEventHandler()
        
        elif handler_type == 'monitoring':
            # Create monitoring event handler with callbacks
            alert_callback = event_handler_config.get('alert_callback')
            dashboard_callback = event_handler_config.get('dashboard_callback')
            metrics_callback = event_handler_config.get('metrics_callback')
            
            return MonitoringCircuitBreakerEventHandler(
                alert_callback=alert_callback,
                dashboard_callback=dashboard_callback,
                metrics_callback=metrics_callback
            )
        
        elif handler_type == 'custom':
            # Allow custom event handler class
            custom_class = event_handler_config.get('class')
            if custom_class:
                try:
                    # Import and instantiate custom class
                    module_name, class_name = custom_class.rsplit('.', 1)
                    module = __import__(module_name, fromlist=[class_name])
                    handler_class = getattr(module, class_name)
                    return handler_class(**event_handler_config.get('config', {}))
                except Exception as e:
                    logger.error(f"Failed to create custom event handler {custom_class}: {e}")
                    return DefaultCircuitBreakerEventHandler()
        
        else:
            logger.warning(f"Unknown event handler type: {handler_type}, using default")
            return DefaultCircuitBreakerEventHandler()
    
    async def execute_adapters(self, query: str, adapter_names: List[str], 
                             context: Optional[AdapterExecutionContext] = None,
                             api_key: Optional[str] = None, **kwargs) -> List[AdapterResult]:
        """
        Execute multiple adapters in parallel with circuit breaker protection.
        
        This is the main entry point that ensures true parallel execution.
        """
        # Create default context if none provided
        if context is None:
            import uuid
            context = AdapterExecutionContext(
                request_id=str(uuid.uuid4()),
                api_key=api_key
            )
        
        log_prefix = context.get_log_prefix()
        
        # Check for shutdown before starting execution
        if self._shutdown_event.is_set():
            logger.warning(f"{log_prefix} Rejecting request - executor is shutting down")
            return [AdapterResult(
                adapter_name=adapter_name,
                success=False,
                data=None,
                error=RuntimeError("Executor is shutting down"),
                execution_time=0.0,
                context=context
            ) for adapter_name in adapter_names]
        
        # Track active request
        self._active_requests.add(context.request_id)
        try:
            if not adapter_names:
                logger.warning(f"{log_prefix} No adapter names provided")
                return []
            
            logger.info(f"{log_prefix} Executing {len(adapter_names)} adapters: {adapter_names}")
            
            # Filter out adapters with open circuits
            available_adapters = []
            circuit_open_results = []
            
            for adapter_name in adapter_names:
                cb = self._get_circuit_breaker(adapter_name)
                if not cb.is_open():
                    available_adapters.append(adapter_name)
                else:
                    logger.info(f"{log_prefix} Skipping adapter {adapter_name} - circuit is open")
                    # Create a result for the circuit-open adapter
                    circuit_open_results.append(AdapterResult(
                        adapter_name=adapter_name,
                        success=False,
                        data=None,
                        error=Exception(f"Circuit is open for adapter {adapter_name}"),
                        execution_time=0.0,
                        context=context
                    ))
            
            if not available_adapters:
                logger.warning(f"{log_prefix} All circuits are open, no adapters available")
                return circuit_open_results
            
            # Enforce max_concurrent batching
            results = circuit_open_results.copy()  # Start with circuit-open results
            for i in range(0, len(available_adapters), self.max_concurrent):
                batch = available_adapters[i:i+self.max_concurrent]
                logger.debug(f"{log_prefix} Executing batch {i//self.max_concurrent + 1}: {batch}")
                tasks = [asyncio.create_task(self._execute_single_adapter(adapter_name, query, context, api_key, **kwargs)) for adapter_name in batch]
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
            
            successful_count = sum(1 for r in results if r.success)
            logger.info(f"{log_prefix} Completed execution: {successful_count}/{len(results)} adapters successful")
            
            return results
            
        finally:
            # Always remove from active requests
            self._active_requests.discard(context.request_id)
    
    async def _execute_single_adapter(self, adapter_name: str, query: str,
                                    context: AdapterExecutionContext,
                                    api_key: Optional[str] = None, **kwargs) -> AdapterResult:
        """Execute a single adapter with timeout and circuit breaker protection"""
        log_prefix = context.get_log_prefix()
        
        cb = self._get_circuit_breaker(adapter_name)
        if cb.is_open():
            logger.debug(f"{log_prefix} Circuit is open for adapter {adapter_name}")
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                data=None,
                error=Exception(f"Circuit is open for adapter {adapter_name}"),
                execution_time=0.0,
                context=context
            )
        
        # Get adapter-specific timeout
        ft_config = self._get_adapter_fault_tolerance_config(adapter_name)
        adapter_timeout = ft_config.get('operation_timeout', self.operation_timeout)
        
        logger.debug(f"{log_prefix} Starting execution of adapter {adapter_name} (timeout: {adapter_timeout}s)")
        start_time = time.time()
        
        try:
            # Apply timeout to the entire operation
            adapter = await asyncio.wait_for(
                self._get_adapter_with_timeout(adapter_name),
                timeout=adapter_timeout * 0.3  # 30% of time for initialization
            )
            
            # Execute the query with remaining timeout
            remaining_timeout = adapter_timeout * 0.7  # 70% for execution
            result = await asyncio.wait_for(
                self._execute_adapter_query(adapter, query, context, api_key, **kwargs),
                timeout=remaining_timeout
            )
            
            # Record success
            execution_time = time.time() - start_time
            cb.record_success(execution_time=execution_time)
            
            logger.debug(f"{log_prefix} Adapter {adapter_name} completed successfully in {execution_time:.2f}s")
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=True,
                data=result,
                execution_time=execution_time,
                context=context
            )
            
        except asyncio.TimeoutError as e:
            execution_time = time.time() - start_time
            cb.record_failure(execution_time=execution_time)
            cb.stats.timeout_calls += 1
            logger.warning(f"{log_prefix} Timeout for adapter {adapter_name} after {execution_time:.2f}s (timeout: {adapter_timeout}s)")
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                error=Exception(f"Timeout for adapter {adapter_name}"),
                execution_time=execution_time,
                context=context
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            cb.record_failure(execution_time=execution_time)
            logger.error(f"{log_prefix} Error in adapter {adapter_name}: {str(e)}")
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                error=e,
                execution_time=execution_time,
                context=context
            )
    
    async def _get_adapter_with_timeout(self, adapter_name: str):
        """Get adapter with proper timeout handling"""
        # If the adapter manager's get_adapter is synchronous, run it in executor
        if asyncio.iscoroutinefunction(self.adapter_manager.get_adapter):
            return await self.adapter_manager.get_adapter(adapter_name)
        else:
            # Run synchronous code in thread pool to prevent blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.thread_pool,
                self.adapter_manager.get_adapter,
                adapter_name
            )
    
    async def _execute_adapter_query(self, adapter, query: str, context: AdapterExecutionContext, 
                                   api_key: Optional[str], **kwargs):
        """Execute adapter query with proper async handling and context propagation"""
        # Add context information to kwargs for adapter consumption
        adapter_kwargs = kwargs.copy()
        adapter_kwargs['request_id'] = context.request_id
        adapter_kwargs['trace_id'] = context.trace_id
        adapter_kwargs['user_id'] = context.user_id
        adapter_kwargs['session_id'] = context.session_id
        adapter_kwargs['correlation_id'] = context.correlation_id
        
        if asyncio.iscoroutinefunction(adapter.get_relevant_context):
            return await adapter.get_relevant_context(query=query, api_key=api_key, **adapter_kwargs)
        else:
            # Run synchronous code in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.thread_pool,
                functools.partial(adapter.get_relevant_context, query=query, api_key=api_key, **adapter_kwargs)
            )
    
    async def _execute_all_strategy(self, tasks: List[asyncio.Task], 
                                  adapter_names: List[str]) -> List[AdapterResult]:
        """Execute all adapters and return all results"""
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        adapter_results = []
        for i, result in enumerate(results):
            if isinstance(result, AdapterResult):
                adapter_results.append(result)
            else:
                # Handle unexpected errors
                adapter_results.append(AdapterResult(
                    adapter_name=adapter_names[i],
                    success=False,
                    error=result if isinstance(result, Exception) else Exception(str(result))
                ))
        
        return adapter_results
    
    async def _execute_first_success_strategy(self, tasks: List[asyncio.Task],
                                            adapter_names: List[str]) -> List[AdapterResult]:
        """Return as soon as one adapter succeeds"""
        results = []
        
        # Use asyncio.as_completed to get results as they complete
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                results.append(result)
                
                if result.success:
                    # Cancel remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    
                    # Wait for cancellations to complete
                    await asyncio.gather(*tasks, return_exceptions=True)
                    
                    return results
                    
            except Exception as e:
                logger.error(f"Error in first_success strategy: {e}")
        
        return results
    
    async def _execute_best_effort_strategy(self, tasks: List[asyncio.Task],
                                          adapter_names: List[str]) -> List[AdapterResult]:
        """Return whatever completes within a reasonable time"""
        # Wait for a shorter timeout
        timeout = self.operation_timeout * 0.8
        
        try:
            # Wait for all tasks with timeout
            done, pending = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED)
            
            results = []
            
            # Process completed tasks
            for task in done:
                try:
                    result = await task
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing task result: {e}")
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                
            return results
            
        except Exception as e:
            logger.error(f"Error in best_effort strategy: {e}")
            return []
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        return {
            name: cb.get_status()
            for name, cb in self.circuit_breakers.items()
        }
    
    def get_adapter_configuration_info(self) -> Dict[str, Any]:
        """Get adapter-specific configuration information for monitoring"""
        adapter_info = {}
        for adapter_name in self.circuit_breakers.keys():
            ft_config = self._get_adapter_fault_tolerance_config(adapter_name)
            adapter_info[adapter_name] = {
                "fault_tolerance": {
                    "operation_timeout": ft_config.get('operation_timeout', self.operation_timeout),
                    "failure_threshold": ft_config.get('failure_threshold', self.failure_threshold),
                    "recovery_timeout": ft_config.get('recovery_timeout', self.recovery_timeout),
                    "success_threshold": ft_config.get('success_threshold', self.success_threshold),
                    "max_recovery_timeout": ft_config.get('max_recovery_timeout', 300.0),
                    "enable_exponential_backoff": ft_config.get('enable_exponential_backoff', True),
                    "max_retries": ft_config.get('max_retries', 3),
                    "retry_delay": ft_config.get('retry_delay', 1.0),
                    "enable_thread_isolation": ft_config.get('enable_thread_isolation', False),
                    "enable_process_isolation": ft_config.get('enable_process_isolation', False)
                }
            }
        return adapter_info
    
    def reset_circuit_breaker(self, adapter_name: str):
        """Reset a specific circuit breaker"""
        if adapter_name in self.circuit_breakers:
            self.circuit_breakers[adapter_name]._close_circuit()
            logger.info(f"Reset circuit breaker for adapter: {adapter_name}")
    
    def force_cleanup_all_circuit_breakers(self):
        """Force cleanup of all circuit breakers"""
        total_cleaned = 0
        for adapter_name, cb in self.circuit_breakers.items():
            cb.force_cleanup()
            total_cleaned += 1
        
        logger.info(f"Forced cleanup of {total_cleaned} circuit breakers")
    
    def get_memory_usage_summary(self) -> Dict[str, Any]:
        """Get memory usage summary for all circuit breakers"""
        total_call_history = 0
        total_transitions = 0
        memory_by_adapter = {}
        
        for adapter_name, cb in self.circuit_breakers.items():
            call_history_size = len(cb.stats.call_history)
            transitions_size = len(cb.stats.state_transitions)
            
            total_call_history += call_history_size
            total_transitions += transitions_size
            
            memory_by_adapter[adapter_name] = {
                "call_history_size": call_history_size,
                "state_transitions_size": transitions_size,
                "last_cleanup": cb._last_cleanup,
                "cleanup_interval": cb.cleanup_interval,
                "retention_period": cb.retention_period
            }
        
        return {
            "total_call_history_records": total_call_history,
            "total_state_transition_records": total_transitions,
            "total_memory_usage_estimate": (total_call_history + total_transitions) * 100,  # Rough estimate in bytes
            "by_adapter": memory_by_adapter
        }
    
    async def cleanup(self):
        """Cleanup resources with graceful shutdown handling"""
        logger.info("Starting graceful shutdown of ParallelAdapterExecutor")
        
        # Signal shutdown to prevent new requests
        self._shutdown_event.set()
        logger.info("Shutdown signal sent - rejecting new requests")
        
        # Wait for active requests to complete with timeout
        if self._active_requests:
            logger.info(f"Waiting for {len(self._active_requests)} active requests to complete")
            wait_time = 0
            check_interval = 0.1  # Check every 100ms
            
            while self._active_requests and wait_time < self._shutdown_timeout:
                await asyncio.sleep(check_interval)
                wait_time += check_interval
                
                # Log progress every 5 seconds
                if int(wait_time) % 5 == 0 and self._active_requests:
                    logger.info(f"Still waiting for {len(self._active_requests)} requests (waited {wait_time:.1f}s)")
            
            if self._active_requests:
                logger.warning(f"Shutdown timeout reached - {len(self._active_requests)} requests still active: {list(self._active_requests)}")
            else:
                logger.info("All active requests completed successfully")
        else:
            logger.info("No active requests to wait for")
        
        # Shutdown thread pool
        logger.info("Shutting down thread pool")
        self.thread_pool.shutdown(wait=True)
        
        # Reset circuit breakers
        logger.info("Resetting circuit breakers")
        for adapter_name in list(self.circuit_breakers.keys()):
            self.circuit_breakers[adapter_name].reset()
        
        logger.info("ParallelAdapterExecutor cleanup completed")
    
    def is_shutting_down(self) -> bool:
        """Check if the executor is in shutdown mode"""
        return self._shutdown_event.is_set()
    
    def get_active_request_count(self) -> int:
        """Get the number of currently active requests"""
        return len(self._active_requests)
    
    def get_active_requests(self) -> List[str]:
        """Get list of currently active request IDs"""
        return list(self._active_requests)