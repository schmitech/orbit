"""
Simplified Parallel Adapter Executor with Circuit Breaker Protection

This module provides a streamlined approach to executing multiple adapters
in parallel with circuit breaker protection and timeout handling.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import functools

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerStats:
    """Simple stats for circuit breaker"""
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

@dataclass
class AdapterResult:
    """Result from adapter execution"""
    adapter_name: str
    success: bool
    data: Any = None
    error: Optional[Exception] = None
    execution_time: float = 0.0
    
class SimpleCircuitBreaker:
    """Simplified circuit breaker for a single adapter"""
    
    def __init__(self, adapter_name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, success_threshold: int = 3):
        self.adapter_name = adapter_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
        
    def is_open(self) -> bool:
        """Check if circuit is open"""
        if self.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if time.time() - self._state_changed_at >= self.recovery_timeout:
                self._transition_to_half_open()
                return False
            return True
        return False
    
    def can_execute(self) -> bool:
        """Check if the circuit allows execution (not open)"""
        return not self.is_open()
    
    def record_success(self, *args, **kwargs):
        """Record a successful call (accepts optional args for compatibility)"""
        self.stats.success_count += 1
        self.stats.total_successes += 1
        self.stats.total_calls += 1
        self.stats.consecutive_successes += 1
        self.stats.consecutive_failures = 0
        self.stats.last_success_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            if self.stats.consecutive_successes >= self.success_threshold:
                self._close_circuit()
        elif self.state == CircuitState.OPEN:
            # If a success occurs in OPEN (shouldn't happen), transition to HALF_OPEN
            self._transition_to_half_open()
    
    def record_failure(self, *args, **kwargs):
        """Record a failed call (accepts optional args for compatibility)"""
        self.stats.failure_count += 1
        self.stats.total_failures += 1
        self.stats.total_calls += 1
        self.stats.consecutive_failures += 1
        self.stats.consecutive_successes = 0
        self.stats.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            if self.stats.consecutive_failures >= self.failure_threshold:
                self._open_circuit()
        elif self.state == CircuitState.HALF_OPEN:
            self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit"""
        self.state = CircuitState.OPEN
        self._state_changed_at = time.time()
        logger.warning(f"Circuit breaker OPENED for adapter: {self.adapter_name}")
    
    def _close_circuit(self):
        """Close the circuit"""
        self.state = CircuitState.CLOSED
        self._state_changed_at = time.time()
        self.stats.consecutive_failures = 0
        self.stats.consecutive_successes = 0
        logger.info(f"Circuit breaker CLOSED for adapter: {self.adapter_name}")
    
    def _transition_to_half_open(self):
        """Transition to half-open state"""
        self.state = CircuitState.HALF_OPEN
        self._state_changed_at = time.time()
        self.stats.consecutive_successes = 0
        logger.info(f"Circuit breaker HALF-OPEN for adapter: {self.adapter_name}")
    
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
            "last_success_time": self.stats.last_success_time
        }
    
    def reset(self):
        """Reset the circuit breaker stats and state"""
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
        logger.info(f"Circuit breaker RESET for adapter: {self.adapter_name}")

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
        }
    
    def _get_circuit_breaker(self, adapter_name: str) -> SimpleCircuitBreaker:
        """Get or create circuit breaker for adapter"""
        if adapter_name not in self.circuit_breakers:
            self.circuit_breakers[adapter_name] = SimpleCircuitBreaker(
                adapter_name,
                self.failure_threshold,
                self.recovery_timeout,
                self.success_threshold
            )
        return self.circuit_breakers[adapter_name]
    
    async def execute_adapters(self, query: str, adapter_names: List[str], 
                             api_key: Optional[str] = None, **kwargs) -> List[AdapterResult]:
        """
        Execute multiple adapters in parallel with circuit breaker protection.
        
        This is the main entry point that ensures true parallel execution.
        """
        if not adapter_names:
            logger.warning("No adapter names provided")
            return []
        
        # Filter out adapters with open circuits
        available_adapters = []
        circuit_open_results = []
        
        for adapter_name in adapter_names:
            cb = self._get_circuit_breaker(adapter_name)
            if not cb.is_open():
                available_adapters.append(adapter_name)
            else:
                logger.info(f"Skipping adapter {adapter_name} - circuit is open")
                # Create a result for the circuit-open adapter
                circuit_open_results.append(AdapterResult(
                    adapter_name=adapter_name,
                    success=False,
                    data=None,
                    error=Exception(f"Circuit is open for adapter {adapter_name}"),
                    execution_time=0.0
                ))
        
        if not available_adapters:
            logger.warning("All circuits are open, no adapters available")
            return circuit_open_results
        
        # Enforce max_concurrent batching
        results = circuit_open_results.copy()  # Start with circuit-open results
        for i in range(0, len(available_adapters), self.max_concurrent):
            batch = available_adapters[i:i+self.max_concurrent]
            tasks = [asyncio.create_task(self._execute_single_adapter(adapter_name, query, api_key, **kwargs)) for adapter_name in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
        
        return results
    
    async def _execute_single_adapter(self, adapter_name: str, query: str,
                                    api_key: Optional[str] = None, **kwargs) -> AdapterResult:
        """Execute a single adapter with timeout and circuit breaker protection"""
        cb = self._get_circuit_breaker(adapter_name)
        if cb.is_open():
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                data=None,
                error=Exception(f"Circuit is open for adapter {adapter_name}"),
                execution_time=0.0
            )
        start_time = time.time()
        
        try:
            # Apply timeout to the entire operation
            adapter = await asyncio.wait_for(
                self._get_adapter_with_timeout(adapter_name),
                timeout=self.operation_timeout * 0.3  # 30% of time for initialization
            )
            
            # Execute the query with remaining timeout
            remaining_timeout = self.operation_timeout * 0.7  # 70% for execution
            result = await asyncio.wait_for(
                self._execute_adapter_query(adapter, query, api_key, **kwargs),
                timeout=remaining_timeout
            )
            
            # Record success
            cb.record_success()
            execution_time = time.time() - start_time
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=True,
                data=result,
                execution_time=execution_time
            )
            
        except asyncio.TimeoutError as e:
            cb.record_failure()
            cb.stats.timeout_calls += 1
            execution_time = time.time() - start_time
            logger.warning(f"Timeout for adapter {adapter_name} after {execution_time:.2f}s")
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                error=Exception(f"Timeout for adapter {adapter_name}"),
                execution_time=execution_time
            )
            
        except Exception as e:
            cb.record_failure()
            execution_time = time.time() - start_time
            logger.error(f"Error in adapter {adapter_name}: {str(e)}")
            
            return AdapterResult(
                adapter_name=adapter_name,
                success=False,
                error=e,
                execution_time=execution_time
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
    
    async def _execute_adapter_query(self, adapter, query: str, api_key: Optional[str], **kwargs):
        """Execute adapter query with proper async handling"""
        if asyncio.iscoroutinefunction(adapter.get_relevant_context):
            return await adapter.get_relevant_context(query=query, api_key=api_key, **kwargs)
        else:
            # Run synchronous code in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.thread_pool,
                functools.partial(adapter.get_relevant_context, query=query, api_key=api_key, **kwargs)
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
    
    def reset_circuit_breaker(self, adapter_name: str):
        """Reset a specific circuit breaker"""
        if adapter_name in self.circuit_breakers:
            self.circuit_breakers[adapter_name]._close_circuit()
            logger.info(f"Reset circuit breaker for adapter: {adapter_name}")
    
    async def cleanup(self):
        """Cleanup resources"""
        self.thread_pool.shutdown(wait=True)
        logger.info("ParallelAdapterExecutor cleaned up")