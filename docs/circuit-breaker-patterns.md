# Circuit Breaker Patterns in ORBIT

This document provides detailed information about circuit breaker implementation patterns, state management, and best practices in ORBIT's fault tolerance system.

## Circuit Breaker Pattern Overview

The Circuit Breaker pattern prevents cascading failures in distributed systems by wrapping calls to external services and monitoring for failures. When failures reach a threshold, the circuit "opens" and subsequent calls fail fast without attempting the operation.

## ORBIT's Circuit Breaker Implementation

### Core Components

#### 1. CircuitState Enumeration

```python
class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open" # Testing if service recovered
```

#### 2. CircuitBreakerStats

Tracks operational metrics for decision making:

```python
@dataclass
class CircuitBreakerStats:
    failure_count: int = 0           # Total failures in current window
    success_count: int = 0           # Total successes in current window
    timeout_calls: int = 0           # Calls that timed out
    consecutive_failures: int = 0     # Consecutive failures (resets on success)
    consecutive_successes: int = 0    # Consecutive successes (resets on failure)
    total_calls: int = 0             # All-time call count
    total_failures: int = 0          # All-time failure count
    total_successes: int = 0         # All-time success count
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
```

#### 3. SimpleCircuitBreaker

```python
class SimpleCircuitBreaker:
    def __init__(self, adapter_name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, success_threshold: int = 3):
        self.adapter_name = adapter_name
        self.failure_threshold = failure_threshold    # Failures to open circuit
        self.recovery_timeout = recovery_timeout      # Time before half-open
        self.success_threshold = success_threshold    # Successes to close circuit
        
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._state_changed_at = time.time()
```

## State Transition Logic

### CLOSED → OPEN

The circuit opens when consecutive failures exceed the threshold:

```python
def record_failure(self, error_type: str = "general"):
    """Record a failed call and update circuit state"""
    self.stats.failure_count += 1
    self.stats.total_failures += 1
    self.stats.total_calls += 1
    self.stats.consecutive_failures += 1
    self.stats.consecutive_successes = 0
    self.stats.last_failure_time = time.time()
    
    # Check if circuit should open
    if (self.state == CircuitState.CLOSED and 
        self.stats.consecutive_failures >= self.failure_threshold):
        self._open_circuit()

def _open_circuit(self):
    """Open the circuit breaker"""
    self.state = CircuitState.OPEN
    self._state_changed_at = time.time()
    logger.warning(f"Circuit breaker OPENED for adapter: {self.adapter_name}")
```

### OPEN → HALF_OPEN

After the recovery timeout, the circuit automatically transitions to half-open:

```python
def is_open(self) -> bool:
    """Check if circuit is open"""
    if self.state == CircuitState.OPEN:
        # Check if we should transition to half-open
        if time.time() - self._state_changed_at >= self.recovery_timeout:
            self._transition_to_half_open()
            return False
        return True
    return False

def _transition_to_half_open(self):
    """Transition from OPEN to HALF_OPEN state"""
    self.state = CircuitState.HALF_OPEN
    self._state_changed_at = time.time()
    logger.info(f"Circuit breaker HALF_OPEN for adapter: {self.adapter_name}")
```

### HALF_OPEN → CLOSED/OPEN

In half-open state, the circuit monitors calls to determine recovery:

```python
def record_success(self):
    """Record a successful call"""
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
        # If success occurs in OPEN state, transition to HALF_OPEN
        self._transition_to_half_open()

def _close_circuit(self):
    """Close the circuit breaker"""
    self.state = CircuitState.CLOSED
    self._state_changed_at = time.time()
    logger.info(f"Circuit breaker CLOSED for adapter: {self.adapter_name}")
```

## Integration with Adapter Execution

### Pre-execution Check

Before executing an adapter, check if the circuit allows execution:

```python
async def _execute_single_adapter(self, adapter_name: str, query: str, **kwargs):
    """Execute a single adapter with circuit breaker protection"""
    cb = self._get_circuit_breaker(adapter_name)
    
    # Fast-fail if circuit is open
    if cb.is_open():
        return AdapterResult(
            adapter_name=adapter_name,
            success=False,
            data=None,
            error=Exception(f"Circuit is open for adapter {adapter_name}"),
            execution_time=0.0
        )
    
    # Proceed with execution...
```

### Post-execution Recording

Record the outcome to update circuit state:

```python
try:
    # Execute adapter
    result = await adapter.get_relevant_context(query, **kwargs)
    
    # Record success
    cb.record_success()
    return AdapterResult(
        adapter_name=adapter_name,
        success=True,
        data=result,
        execution_time=execution_time
    )
    
except asyncio.TimeoutError:
    # Record timeout failure
    cb.record_failure()
    cb.stats.timeout_calls += 1
    return AdapterResult(
        adapter_name=adapter_name,
        success=False,
        error=Exception(f"Timeout for adapter {adapter_name}"),
        execution_time=execution_time
    )
    
except Exception as e:
    # Record general failure
    cb.record_failure()
    return AdapterResult(
        adapter_name=adapter_name,
        success=False,
        error=e,
        execution_time=execution_time
    )
```

## Circuit Breaker Management

### Per-Adapter Circuit Breakers

Each adapter gets its own circuit breaker instance:

```python
def _get_circuit_breaker(self, adapter_name: str) -> SimpleCircuitBreaker:
    """Get or create circuit breaker for adapter"""
    if adapter_name not in self.circuit_breakers:
        self.circuit_breakers[adapter_name] = SimpleCircuitBreaker(
            adapter_name=adapter_name,
            failure_threshold=self.failure_threshold,
            recovery_timeout=self.recovery_timeout,
            success_threshold=self.success_threshold
        )
    return self.circuit_breakers[adapter_name]
```

### Manual Circuit Management

Provide administrative controls for circuit breakers:

```python
def reset_circuit_breaker(self, adapter_name: str):
    """Manually reset a circuit breaker"""
    if adapter_name in self.circuit_breakers:
        cb = self.circuit_breakers[adapter_name]
        cb._close_circuit()
        cb.stats = CircuitBreakerStats()  # Reset statistics
        logger.info(f"Manually reset circuit breaker for: {adapter_name}")

def force_open_circuit_breaker(self, adapter_name: str):
    """Manually open a circuit breaker"""
    cb = self._get_circuit_breaker(adapter_name)
    cb._open_circuit()
    logger.warning(f"Manually opened circuit breaker for: {adapter_name}")
```

## Advanced Patterns

### Sliding Window Failure Detection

For more sophisticated failure detection, implement a sliding window:

```python
class SlidingWindowCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, window_size: int = 10, 
                 failure_rate_threshold: float = 0.5, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.recent_calls = deque(maxlen=window_size)
    
    def should_open_circuit(self) -> bool:
        """Check if circuit should open based on failure rate"""
        if len(self.recent_calls) < self.window_size:
            return False
            
        failure_rate = sum(1 for call in self.recent_calls if not call) / len(self.recent_calls)
        return failure_rate >= self.failure_rate_threshold
```

### Adaptive Timeouts

Adjust timeouts based on historical performance:

```python
class AdaptiveTimeoutCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.response_times = deque(maxlen=100)
        self.base_timeout = 30.0
    
    def get_adaptive_timeout(self) -> float:
        """Calculate timeout based on recent response times"""
        if not self.response_times:
            return self.base_timeout
            
        avg_time = sum(self.response_times) / len(self.response_times)
        p95_time = sorted(self.response_times)[int(len(self.response_times) * 0.95)]
        
        # Set timeout to 2x the 95th percentile response time
        return max(self.base_timeout, p95_time * 2)
```

### Bulkhead Pattern Integration

Combine circuit breakers with resource isolation:

```python
class BulkheadCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, max_concurrent_calls: int = 5, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.semaphore = asyncio.Semaphore(max_concurrent_calls)
        self.active_calls = 0
    
    async def execute_with_bulkhead(self, func, *args, **kwargs):
        """Execute function with both circuit breaker and bulkhead protection"""
        if self.is_open():
            raise CircuitOpenException(f"Circuit open for {self.adapter_name}")
        
        try:
            async with self.semaphore:
                self.active_calls += 1
                try:
                    result = await func(*args, **kwargs)
                    self.record_success()
                    return result
                finally:
                    self.active_calls -= 1
        except Exception as e:
            self.record_failure()
            raise
```

## Monitoring and Metrics

### Health Status Reporting

```python
def get_status(self) -> Dict[str, Any]:
    """Get comprehensive circuit breaker status"""
    return {
        "adapter_name": self.adapter_name,
        "state": self.state.value,
        "stats": {
            "total_calls": self.stats.total_calls,
            "success_rate": self._calculate_success_rate(),
            "failure_rate": self._calculate_failure_rate(),
            "consecutive_failures": self.stats.consecutive_failures,
            "consecutive_successes": self.stats.consecutive_successes,
            "timeout_calls": self.stats.timeout_calls,
            "last_failure": self.stats.last_failure_time,
            "last_success": self.stats.last_success_time
        },
        "config": {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "success_threshold": self.success_threshold
        },
        "time_in_current_state": time.time() - self._state_changed_at
    }
```

### Prometheus Metrics Integration

```python
from prometheus_client import Counter, Histogram, Gauge

class MetricsCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, **kwargs):
        super().__init__(adapter_name, **kwargs)
        
        self.call_counter = Counter(
            'circuit_breaker_calls_total',
            'Total circuit breaker calls',
            ['adapter', 'result']
        )
        
        self.state_gauge = Gauge(
            'circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=half_open, 2=open)',
            ['adapter']
        )
        
        self.response_time_histogram = Histogram(
            'circuit_breaker_response_time_seconds',
            'Response time distribution',
            ['adapter']
        )
    
    def record_success(self):
        super().record_success()
        self.call_counter.labels(adapter=self.adapter_name, result='success').inc()
        self._update_state_metric()
    
    def record_failure(self):
        super().record_failure()
        self.call_counter.labels(adapter=self.adapter_name, result='failure').inc()
        self._update_state_metric()
```

## Configuration Best Practices

### Environment-Specific Settings

```yaml
# Development
fault_tolerance:
  failure_threshold: 3          # Fail fast for quick feedback
  recovery_timeout: 10.0        # Quick recovery for testing
  success_threshold: 1          # Single success to close

# Production
fault_tolerance:
  failure_threshold: 5          # More tolerant of transient issues
  recovery_timeout: 60.0        # Longer recovery time
  success_threshold: 3          # Multiple successes required
```

### Adapter-Specific Configuration

```yaml
fault_tolerance:
  adapters:
    slow-database-adapter:
      failure_threshold: 10     # Database might be slower
      recovery_timeout: 120.0   # Longer recovery time
      timeout: 60.0             # Generous timeout
      
    external-api-adapter:
      failure_threshold: 3      # API failures should trigger quickly
      recovery_timeout: 30.0    # Quick recovery attempts
      timeout: 10.0             # Strict timeout
```

## Testing Circuit Breaker Behavior

### Unit Testing

```python
import pytest
import asyncio
from unittest.mock import AsyncMock

class TestCircuitBreaker:
    def test_circuit_opens_after_threshold_failures(self):
        cb = SimpleCircuitBreaker("test", failure_threshold=3)
        
        # Record failures
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
    
    def test_circuit_transitions_to_half_open(self):
        cb = SimpleCircuitBreaker("test", recovery_timeout=0.1)
        
        # Open circuit
        cb._open_circuit()
        
        # Wait for recovery timeout
        time.sleep(0.2)
        
        # Check should transition to half-open
        assert not cb.is_open()
        assert cb.state == CircuitState.HALF_OPEN
```

### Integration Testing

```python
async def test_circuit_breaker_with_failing_adapter():
    # Create adapter that always fails
    failing_adapter = AsyncMock()
    failing_adapter.get_relevant_context.side_effect = Exception("Test failure")
    
    # Execute multiple times to trigger circuit breaker
    results = []
    for i in range(10):
        result = await executor.execute_adapters(f"query {i}", ["failing-adapter"])
        results.append(result)
    
    # Verify circuit opened after threshold
    cb = executor._get_circuit_breaker("failing-adapter")
    assert cb.state == CircuitState.OPEN
    
    # Verify fast failures
    fast_fail_results = [r for r in results[-3:] if "circuit" in str(r[0].error).lower()]
    assert len(fast_fail_results) > 0
```

This circuit breaker implementation provides robust failure isolation while maintaining system responsiveness and enabling quick recovery when services become healthy again.