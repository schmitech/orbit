"""
Circuit Breaker Service for Adapter Fault Tolerance

This module provides a circuit breaker pattern implementation specifically designed
for retriever adapters to prevent cascading failures and provide system isolation.

Key Features:
- Timeout protection for adapter operations
- Failure tracking and automatic recovery
- Health monitoring and metrics
- Thread/process isolation support
- Configurable thresholds and behaviors
- Real-time adapter health reporting
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
import weakref
from datetime import datetime, timedelta
import threading
import multiprocessing as mp

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service has recovered

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    # Timeout settings
    operation_timeout: float = 30.0  # Max time for single operation
    initialization_timeout: float = 60.0  # Max time for adapter initialization
    
    # Failure thresholds
    failure_threshold: int = 5  # Number of failures before opening circuit
    success_threshold: int = 3  # Number of successes needed to close circuit
    
    # Time windows
    failure_window: float = 300.0  # Time window for counting failures (5 min)
    recovery_timeout: float = 60.0  # Time before attempting recovery
    
    # Health check settings
    health_check_interval: float = 30.0  # Health check frequency
    health_check_timeout: float = 10.0  # Health check timeout
    
    # Isolation settings
    use_thread_isolation: bool = True  # Use thread pool for isolation
    use_process_isolation: bool = False  # Use process pool for isolation
    max_workers: int = 5  # Max workers for thread/process pools
    
    # Retry settings
    max_retries: int = 2  # Max retry attempts
    retry_delay: float = 1.0  # Delay between retries
    retry_backoff: float = 2.0  # Backoff multiplier
    
    # Monitoring settings
    enable_metrics: bool = True  # Enable performance metrics
    metrics_window: float = 3600.0  # Metrics time window (1 hour)

@dataclass
class OperationMetrics:
    """Metrics for adapter operations"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_calls: int = 0
    avg_response_time: float = 0.0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    def reset(self):
        """Reset metrics"""
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.timeout_calls = 0
        self.avg_response_time = 0.0
        self.consecutive_failures = 0
        self.consecutive_successes = 0

@dataclass
class CircuitBreakerState:
    """Current state of a circuit breaker"""
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    failure_count: int = 0
    success_count: int = 0
    state_change_time: float = field(default_factory=time.time)
    
    def reset_failure_count(self):
        """Reset failure count"""
        self.failure_count = 0
        self.success_count = 0

class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors"""
    pass

class CircuitOpenError(CircuitBreakerError):
    """Raised when circuit is open"""
    pass

class OperationTimeoutError(CircuitBreakerError):
    """Raised when operation times out"""
    pass

class AdapterCircuitBreaker:
    """
    Circuit breaker for individual adapters with comprehensive fault tolerance.
    
    This class provides:
    - Timeout protection for operations
    - Failure tracking and circuit opening
    - Health monitoring and recovery
    - Thread/process isolation
    - Performance metrics
    """
    
    def __init__(self, adapter_name: str, config: CircuitBreakerConfig):
        self.adapter_name = adapter_name
        self.config = config
        self.state = CircuitBreakerState()
        self.metrics = OperationMetrics()
        self.lock = threading.RLock()
        self.executor = None
        self.process_executor = None
        self.health_check_task = None
        self.response_times = []  # For calculating average response time
        
        # Initialize executors based on configuration
        self._initialize_executors()
        
        logger.info(f"Circuit breaker initialized for adapter: {adapter_name}")
    
    def _initialize_executors(self):
        """Initialize thread/process executors for isolation"""
        if self.config.use_thread_isolation:
            self.executor = ThreadPoolExecutor(
                max_workers=self.config.max_workers,
                thread_name_prefix=f"adapter-{self.adapter_name}"
            )
            logger.info(f"Thread pool executor initialized for {self.adapter_name}")
        
        if self.config.use_process_isolation:
            self.process_executor = ProcessPoolExecutor(
                max_workers=self.config.max_workers
            )
            logger.info(f"Process pool executor initialized for {self.adapter_name}")
    
    async def execute_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute an operation with circuit breaker protection.
        
        Args:
            operation: The operation to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Result of the operation
            
        Raises:
            CircuitOpenError: If circuit is open
            OperationTimeoutError: If operation times out
            Exception: Any other exception from the operation
        """
        # Check circuit state
        if self.state.state == CircuitState.OPEN:
            if not self._should_attempt_reset():
                raise CircuitOpenError(f"Circuit breaker is OPEN for adapter {self.adapter_name}")
            else:
                # Transition to half-open
                self._transition_to_half_open()
        
        start_time = time.time()
        
        try:
            # Execute operation with timeout and isolation
            result = await self._execute_with_isolation(operation, *args, **kwargs)
            
            # Record success
            execution_time = time.time() - start_time
            self._record_success(execution_time)
            
            return result
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            self._record_timeout(execution_time)
            raise OperationTimeoutError(f"Operation timed out after {execution_time:.2f}s for adapter {self.adapter_name}")
            
        except Exception as e:
            execution_time = time.time() - start_time
            self._record_failure(execution_time, e)
            raise
    
    async def _execute_with_isolation(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with appropriate isolation level"""
        timeout = self.config.operation_timeout
        
        if self.config.use_process_isolation and self.process_executor:
            # Process isolation - highest isolation level
            loop = asyncio.get_event_loop()
            try:
                future = self.process_executor.submit(operation, *args, **kwargs)
                return await asyncio.wait_for(
                    loop.run_in_executor(None, future.result),
                    timeout=timeout
                )
            except FutureTimeoutError:
                # Cancel the future if possible
                future.cancel()
                raise asyncio.TimeoutError()
                
        elif self.config.use_thread_isolation and self.executor:
            # Thread isolation - moderate isolation level
            if asyncio.iscoroutinefunction(operation):
                # For async operations, we can't use thread executor directly
                # Instead, run with timeout protection only
                return await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout)
            else:
                # For sync operations, use thread executor
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(self.executor, operation, *args, **kwargs),
                    timeout=timeout
                )
        else:
            # No isolation - just timeout protection
            if asyncio.iscoroutinefunction(operation):
                return await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout)
            else:
                # Run sync operation in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, operation, *args, **kwargs),
                    timeout=timeout
                )
    
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit"""
        if not self.state.last_failure_time:
            return True
        
        time_since_failure = time.time() - self.state.last_failure_time
        return time_since_failure >= self.config.recovery_timeout
    
    def _transition_to_half_open(self):
        """Transition circuit to half-open state"""
        with self.lock:
            self.state.state = CircuitState.HALF_OPEN
            self.state.state_change_time = time.time()
            self.state.success_count = 0
            logger.info(f"Circuit breaker transitioned to HALF_OPEN for adapter {self.adapter_name}")
    
    def _record_success(self, execution_time: float):
        """Record successful operation"""
        with self.lock:
            current_time = time.time()
            self.metrics.total_calls += 1
            self.metrics.successful_calls += 1
            self.metrics.consecutive_successes += 1
            self.metrics.consecutive_failures = 0
            self.metrics.last_success_time = current_time
            
            # Update average response time
            self.response_times.append(execution_time)
            if len(self.response_times) > 100:  # Keep only last 100 measurements
                self.response_times = self.response_times[-100:]
            self.metrics.avg_response_time = sum(self.response_times) / len(self.response_times)
            
            # Update circuit state
            self.state.last_success_time = current_time
            self.state.success_count += 1
            
            # Check if we should close the circuit
            if self.state.state == CircuitState.HALF_OPEN:
                if self.state.success_count >= self.config.success_threshold:
                    self._close_circuit()
                    
    def _record_failure(self, execution_time: float, error: Exception):
        """Record failed operation"""
        with self.lock:
            current_time = time.time()
            self.metrics.total_calls += 1
            self.metrics.failed_calls += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = current_time
            
            # Update circuit state
            self.state.last_failure_time = current_time
            self.state.failure_count += 1
            
            # Check if we should open the circuit
            if self.state.state == CircuitState.CLOSED:
                if self.state.failure_count >= self.config.failure_threshold:
                    self._open_circuit()
            elif self.state.state == CircuitState.HALF_OPEN:
                # Any failure in half-open state opens the circuit
                self._open_circuit()
                
            logger.warning(f"Operation failed for adapter {self.adapter_name}: {error}")
    
    def _record_timeout(self, execution_time: float):
        """Record timeout operation"""
        with self.lock:
            current_time = time.time()
            self.metrics.total_calls += 1
            self.metrics.timeout_calls += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = current_time
            
            # Treat timeouts as failures for circuit breaking
            self.state.last_failure_time = current_time
            self.state.failure_count += 1
            
            if self.state.state == CircuitState.CLOSED:
                if self.state.failure_count >= self.config.failure_threshold:
                    self._open_circuit()
            elif self.state.state == CircuitState.HALF_OPEN:
                self._open_circuit()
    
    def _close_circuit(self):
        """Close the circuit (normal operation)"""
        with self.lock:
            self.state.state = CircuitState.CLOSED
            self.state.state_change_time = time.time()
            self.state.reset_failure_count()
            logger.info(f"Circuit breaker CLOSED for adapter {self.adapter_name}")
    
    def _open_circuit(self):
        """Open the circuit (failing fast)"""
        with self.lock:
            self.state.state = CircuitState.OPEN
            self.state.state_change_time = time.time()
            logger.error(f"Circuit breaker OPENED for adapter {self.adapter_name}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of the adapter"""
        with self.lock:
            success_rate = 0.0
            if self.metrics.total_calls > 0:
                success_rate = self.metrics.successful_calls / self.metrics.total_calls
            
            return {
                "adapter_name": self.adapter_name,
                "circuit_state": self.state.state.value,
                "success_rate": success_rate,
                "total_calls": self.metrics.total_calls,
                "successful_calls": self.metrics.successful_calls,
                "failed_calls": self.metrics.failed_calls,
                "timeout_calls": self.metrics.timeout_calls,
                "avg_response_time": self.metrics.avg_response_time,
                "consecutive_failures": self.metrics.consecutive_failures,
                "consecutive_successes": self.metrics.consecutive_successes,
                "last_success_time": self.metrics.last_success_time,
                "last_failure_time": self.metrics.last_failure_time,
                "state_change_time": self.state.state_change_time
            }
    
    def reset_metrics(self):
        """Reset all metrics"""
        with self.lock:
            self.metrics.reset()
            self.response_times.clear()
            logger.info(f"Metrics reset for adapter {self.adapter_name}")
    
    def force_open(self):
        """Force circuit to open (for testing/maintenance)"""
        with self.lock:
            self._open_circuit()
            logger.info(f"Circuit breaker FORCE OPENED for adapter {self.adapter_name}")
    
    def force_close(self):
        """Force circuit to close (for testing/maintenance)"""
        with self.lock:
            self._close_circuit()
            logger.info(f"Circuit breaker FORCE CLOSED for adapter {self.adapter_name}")
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        if self.executor:
            self.executor.shutdown(wait=True)
            
        if self.process_executor:
            self.process_executor.shutdown(wait=True)
            
        logger.info(f"Circuit breaker cleaned up for adapter {self.adapter_name}")

class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers with centralized configuration and monitoring.
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.circuit_breakers: Dict[str, AdapterCircuitBreaker] = {}
        self.lock = threading.RLock()
        self.health_monitor_task = None
        self.metrics_history = []
        
        if config.enable_metrics:
            self._start_health_monitoring()
    
    def get_circuit_breaker(self, adapter_name: str) -> AdapterCircuitBreaker:
        """Get or create circuit breaker for an adapter"""
        with self.lock:
            if adapter_name not in self.circuit_breakers:
                self.circuit_breakers[adapter_name] = AdapterCircuitBreaker(adapter_name, self.config)
                logger.info(f"Created new circuit breaker for adapter: {adapter_name}")
            return self.circuit_breakers[adapter_name]
    
    def get_all_health_status(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all adapters"""
        with self.lock:
            return {
                name: breaker.get_health_status()
                for name, breaker in self.circuit_breakers.items()
            }
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get system-wide health summary"""
        with self.lock:
            if not self.circuit_breakers:
                return {
                    "total_adapters": 0,
                    "healthy_adapters": 0,
                    "unhealthy_adapters": 0,
                    "system_health": "unknown"
                }
            
            total_adapters = len(self.circuit_breakers)
            healthy_adapters = sum(
                1 for breaker in self.circuit_breakers.values()
                if breaker.state.state == CircuitState.CLOSED
            )
            unhealthy_adapters = total_adapters - healthy_adapters
            
            system_health = "healthy" if unhealthy_adapters == 0 else "degraded"
            if unhealthy_adapters == total_adapters:
                system_health = "unhealthy"
            
            return {
                "total_adapters": total_adapters,
                "healthy_adapters": healthy_adapters,
                "unhealthy_adapters": unhealthy_adapters,
                "system_health": system_health,
                "timestamp": time.time()
            }
    
    def _start_health_monitoring(self):
        """Start background health monitoring"""
        if self.health_monitor_task is None:
            self.health_monitor_task = asyncio.create_task(self._health_monitor_loop())
    
    async def _health_monitor_loop(self):
        """Background health monitoring loop"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                # Collect health metrics
                health_status = self.get_all_health_status()
                system_summary = self.get_system_health_summary()
                
                # Store metrics history
                self.metrics_history.append({
                    "timestamp": time.time(),
                    "health_status": health_status,
                    "system_summary": system_summary
                })
                
                # Keep only recent metrics
                cutoff_time = time.time() - self.config.metrics_window
                self.metrics_history = [
                    m for m in self.metrics_history
                    if m["timestamp"] >= cutoff_time
                ]
                
                # Log system health if degraded
                if system_summary["system_health"] != "healthy":
                    logger.warning(f"System health: {system_summary['system_health']} - "
                                 f"{system_summary['unhealthy_adapters']}/{system_summary['total_adapters']} adapters unhealthy")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
    
    async def cleanup(self):
        """Cleanup all circuit breakers"""
        if self.health_monitor_task:
            self.health_monitor_task.cancel()
            try:
                await self.health_monitor_task
            except asyncio.CancelledError:
                pass
        
        cleanup_tasks = []
        for breaker in self.circuit_breakers.values():
            cleanup_tasks.append(breaker.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        self.circuit_breakers.clear()
        logger.info("Circuit breaker manager cleaned up")

# Global circuit breaker manager instance
_circuit_breaker_manager: Optional[CircuitBreakerManager] = None

def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get the global circuit breaker manager instance"""
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        raise RuntimeError("Circuit breaker manager not initialized")
    return _circuit_breaker_manager

def initialize_circuit_breaker_manager(config: CircuitBreakerConfig):
    """Initialize the global circuit breaker manager"""
    global _circuit_breaker_manager
    _circuit_breaker_manager = CircuitBreakerManager(config)
    logger.info("Circuit breaker manager initialized")

async def cleanup_circuit_breaker_manager():
    """Cleanup the global circuit breaker manager"""
    global _circuit_breaker_manager
    if _circuit_breaker_manager:
        await _circuit_breaker_manager.cleanup()
        _circuit_breaker_manager = None
        logger.info("Circuit breaker manager cleaned up")


class CircuitBreakerService:
    """
    Circuit Breaker Service - High-level interface for circuit breaker functionality.
    
    This service provides a simplified interface to the circuit breaker system,
    wrapping the CircuitBreakerManager for easier integration with other services.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Circuit Breaker Service.
        
        Args:
            config: Configuration dictionary containing circuit breaker settings
        """
        self.config = config
        self.global_circuit_breaker = None
        
        # Extract circuit breaker configuration
        fault_tolerance_config = config.get('fault_tolerance', {})
        circuit_breaker_config = fault_tolerance_config.get('circuit_breaker', {})
        
        # Create circuit breaker configuration
        cb_config = CircuitBreakerConfig(
            failure_threshold=circuit_breaker_config.get('failure_threshold', 5),
            recovery_timeout=circuit_breaker_config.get('recovery_timeout', 60.0),
            success_threshold=circuit_breaker_config.get('success_threshold', 3),
            operation_timeout=circuit_breaker_config.get('timeout', 30.0),
            failure_window=circuit_breaker_config.get('failure_window', 300.0),
            health_check_interval=circuit_breaker_config.get('health_check_interval', 30.0),
            health_check_timeout=circuit_breaker_config.get('health_check_timeout', 10.0),
            use_thread_isolation=circuit_breaker_config.get('use_thread_isolation', True),
            use_process_isolation=circuit_breaker_config.get('use_process_isolation', False),
            max_workers=circuit_breaker_config.get('max_workers', 5),
            max_retries=circuit_breaker_config.get('max_retries', 2),
            retry_delay=circuit_breaker_config.get('retry_delay', 1.0),
            retry_backoff=circuit_breaker_config.get('retry_backoff', 2.0),
            enable_metrics=circuit_breaker_config.get('enable_metrics', True),
            metrics_window=circuit_breaker_config.get('metrics_window', 3600.0)
        )
        
        # Initialize the circuit breaker manager
        self.circuit_breaker_manager = CircuitBreakerManager(cb_config)
        
        logger.info("Circuit Breaker Service initialized")
    
    def get_circuit_breaker(self, adapter_name: str) -> AdapterCircuitBreaker:
        """
        Get or create a circuit breaker for an adapter.
        
        Args:
            adapter_name: Name of the adapter
            
        Returns:
            AdapterCircuitBreaker instance
        """
        return self.circuit_breaker_manager.get_circuit_breaker(adapter_name)
    
    @property
    def circuit_breakers(self) -> Dict[str, AdapterCircuitBreaker]:
        """
        Get all circuit breakers.
        
        Returns:
            Dictionary of adapter names to circuit breakers
        """
        return self.circuit_breaker_manager.circuit_breakers
    
    def get_all_circuit_breakers(self) -> Dict[str, AdapterCircuitBreaker]:
        """
        Get all circuit breakers.
        
        Returns:
            Dictionary of adapter names to circuit breakers
        """
        return self.circuit_breaker_manager.circuit_breakers
    
    def get_circuit_breaker_states(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the states of all circuit breakers.
        
        Returns:
            Dictionary of adapter names to their circuit breaker states
        """
        return self.circuit_breaker_manager.get_all_health_status()
    
    def reset_circuit_breaker(self, adapter_name: str) -> None:
        """
        Reset a specific circuit breaker.
        
        Args:
            adapter_name: Name of the adapter to reset
        """
        if adapter_name in self.circuit_breaker_manager.circuit_breakers:
            breaker = self.circuit_breaker_manager.circuit_breakers[adapter_name]
            breaker.force_close()
            breaker.reset_metrics()
            logger.info(f"Reset circuit breaker for adapter: {adapter_name}")
    
    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        for adapter_name in self.circuit_breaker_manager.circuit_breakers:
            self.reset_circuit_breaker(adapter_name)
        logger.info("Reset all circuit breakers")
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status of the circuit breaker service.
        
        Returns:
            Health status dictionary
        """
        return self.circuit_breaker_manager.get_system_health_summary()
    
    async def cleanup(self) -> None:
        """Cleanup the circuit breaker service."""
        await self.circuit_breaker_manager.cleanup()
        logger.info("Circuit Breaker Service cleaned up") 