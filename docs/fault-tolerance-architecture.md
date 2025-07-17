# Fault Tolerance Architecture

This document describes ORBIT's fault tolerance system, including circuit breaker patterns, parallel execution, and error handling mechanisms.

## Overview

ORBIT's fault tolerance system provides resilient adapter execution through:

- **Circuit Breaker Pattern**: Prevents cascading failures by isolating failing adapters
- **Parallel Execution**: True async execution of multiple adapters without blocking
- **Timeout Management**: Configurable timeouts with proper resource cleanup
- **Health Monitoring**: Real-time status monitoring and circuit breaker management
- **Graceful Degradation**: Continue operation when some adapters fail

## Architecture Components

### 1. FaultTolerantAdapterManager

The main entry point that coordinates between the base adapter manager and fault tolerance features.

```python
# Location: server/services/fault_tolerant_adapter_manager.py
class FaultTolerantAdapterManager:
    def __init__(self, config: Dict[str, Any], app_state: Any):
        self.fault_tolerance_enabled = self._is_enabled(
            config.get('fault_tolerance', {}).get('enabled', False)
        )
        
        if self.fault_tolerance_enabled:
            self.parallel_executor = ParallelAdapterExecutor(
                self.base_adapter_manager, config
            )
```

**Key Responsibilities:**
- Determine whether to use fault-tolerant or sequential execution
- Coordinate between base adapter manager and parallel executor
- Combine results from multiple adapters
- Provide health status and circuit breaker management

### 2. ParallelAdapterExecutor

Executes multiple adapters in parallel with circuit breaker protection.

```python
# Location: server/services/parallel_adapter_executor.py
class ParallelAdapterExecutor:
    async def execute_adapters(self, query: str, adapter_names: List[str], **kwargs):
        # Filter adapters with open circuits
        available_adapters = []
        circuit_open_results = []
        
        for adapter_name in adapter_names:
            cb = self._get_circuit_breaker(adapter_name)
            if not cb.is_open():
                available_adapters.append(adapter_name)
            else:
                # Return error result for open circuits
                circuit_open_results.append(AdapterResult(...))
        
        # Execute available adapters in parallel
        tasks = [
            asyncio.create_task(self._execute_single_adapter(name, query, **kwargs))
            for name in available_adapters
        ]
        batch_results = await asyncio.gather(*tasks)
        
        return circuit_open_results + batch_results
```

**Key Features:**
- True parallel execution using `asyncio.create_task()`
- Circuit breaker checking before execution
- Timeout handling with proper resource cleanup
- Batched execution to respect concurrency limits

### 3. SimpleCircuitBreaker

Implements the circuit breaker pattern for individual adapters.

```python
class SimpleCircuitBreaker:
    def __init__(self, adapter_name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, success_threshold: int = 3):
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        
    def is_open(self) -> bool:
        if self.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if time.time() - self._state_changed_at >= self.recovery_timeout:
                self._transition_to_half_open()
                return False
            return True
        return False
```

**Circuit States:**
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Circuit is open, requests fail fast
- **HALF_OPEN**: Testing if service has recovered

**State Transitions:**
- CLOSED → OPEN: When failure threshold is exceeded
- OPEN → HALF_OPEN: After recovery timeout expires
- HALF_OPEN → CLOSED: When success threshold is met
- HALF_OPEN → OPEN: On any failure during testing

### 4. Health Monitoring

Provides real-time monitoring and management of circuit breakers.

```python
# Location: server/routes/health_routes.py
@router.get("/health/adapters")
async def get_adapter_health():
    """Get health status of all adapters"""
    
@router.post("/health/adapters/{adapter_name}/reset")
async def reset_circuit_breaker(adapter_name: str):
    """Reset circuit breaker for specific adapter"""
```

## Configuration

### Basic Configuration

```yaml
fault_tolerance:
  enabled: true
  
  # Circuit breaker settings
  failure_threshold: 5          # Failures before opening circuit
  recovery_timeout: 60.0        # Seconds before trying half-open
  success_threshold: 3          # Successes to close circuit
  
  # Execution settings
  execution:
    strategy: "all"             # "all", "first_success", "best_effort"
    timeout: 30.0               # Total timeout per adapter
    max_concurrent_adapters: 10 # Concurrent execution limit
  
  # Health monitoring
  health_monitoring:
    enabled: true
    check_interval: 30.0        # Health check frequency
    history_size: 100           # Number of recent calls to track
```

### Execution Strategies

#### "all" Strategy (Default)
- Executes all available adapters in parallel
- Waits for all to complete or timeout
- Returns combined results from all successful adapters
- Best for: Comprehensive result gathering

#### "first_success" Strategy
- Executes adapters in parallel
- Returns as soon as first adapter succeeds
- Cancels remaining executions
- Best for: Speed and quick responses

#### "best_effort" Strategy
- Executes adapters in parallel
- Returns whatever completes within timeout
- Doesn't wait for slower adapters
- Best for: Balanced performance and completeness

### Timeout Allocation

The system allocates timeout budget efficiently:

```python
# 30% for adapter initialization
initialization_timeout = total_timeout * 0.3

# 70% for query execution
execution_timeout = total_timeout * 0.7
```

## Error Handling

### Timeout Handling

```python
try:
    result = await asyncio.wait_for(
        adapter.get_relevant_context(query, **kwargs),
        timeout=execution_timeout
    )
    cb.record_success()
    return AdapterResult(success=True, data=result, ...)
    
except asyncio.TimeoutError:
    cb.record_failure()
    cb.stats.timeout_calls += 1
    return AdapterResult(
        success=False, 
        error=Exception(f"Timeout for adapter {adapter_name}"),
        ...
    )
```

### Circuit Breaker Error Handling

```python
def record_failure(self, error_type: str = "general"):
    """Record a failed call and update circuit state"""
    self.stats.failure_count += 1
    self.stats.consecutive_failures += 1
    self.stats.consecutive_successes = 0
    
    # Check if we should open the circuit
    if (self.state == CircuitState.CLOSED and 
        self.stats.consecutive_failures >= self.failure_threshold):
        self._open_circuit()
```

### Graceful Degradation

When adapters fail:

1. **Individual Failures**: Other adapters continue execution
2. **Circuit Open**: Fast-fail with cached error responses
3. **All Adapters Fail**: Return empty results with error logging
4. **Partial Success**: Return successful results, log failures

## Monitoring and Observability

### Circuit Breaker Statistics

Each circuit breaker tracks:

```python
@dataclass
class CircuitBreakerStats:
    failure_count: int = 0
    success_count: int = 0
    timeout_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
```

### Health Endpoints

```bash
# Get overall system health
GET /health/system

# Get adapter-specific health
GET /health/adapters

# Get specific adapter status
GET /health/adapters/{adapter_name}

# Reset circuit breaker
POST /health/adapters/{adapter_name}/reset

# Get circuit breaker statistics
GET /health/adapters/{adapter_name}/stats
```

### Logging

The system provides structured logging for:

- Circuit state changes
- Adapter execution timing
- Timeout occurrences
- Error patterns
- Recovery events

```python
logger.warning(f"Circuit breaker OPENED for adapter: {adapter_name}")
logger.info(f"Circuit breaker CLOSED for adapter: {adapter_name}")
logger.warning(f"Timeout for adapter {adapter_name} after {execution_time:.2f}s")
```

## Performance Characteristics

### Execution Timing

With fault tolerance enabled:

```
Total Request Time = max(adapter_times) + coordination_overhead

Without blocking:
- 3 adapters taking 1s each = ~1s total (parallel)
- vs 3s total (sequential)

With timeouts:
- Slow adapter (10s) with 5s timeout = 5s max
- Other adapters continue normally
```

### Memory Usage

- Circuit breaker stats: ~1KB per adapter
- Parallel execution: Additional task overhead
- Thread pool: Configurable worker threads

### Throughput

Concurrent request handling:

- Multiple requests can execute simultaneously
- Each request runs adapters in parallel
- Circuit breakers prevent resource waste on failing adapters

## Best Practices

### Configuration Guidelines

1. **Failure Threshold**: Start with 5, adjust based on adapter reliability
2. **Recovery Timeout**: 30-60 seconds for most use cases
3. **Execution Timeout**: Based on acceptable response time (10-30s)
4. **Concurrency**: Start with 2x CPU cores, monitor resource usage

### Monitoring

1. Track circuit breaker state changes
2. Monitor timeout frequency by adapter
3. Set up alerts for high failure rates
4. Track response time distributions

### Error Handling

1. Implement proper logging in adapters
2. Use specific exception types for different failure modes
3. Provide fallback responses when possible
4. Document expected failure patterns

### Testing

1. Test with simulated slow/failing adapters
2. Verify circuit breaker state transitions
3. Test timeout behavior under load
4. Validate parallel execution performance

## Migration from Legacy System

If migrating from a previous fault tolerance implementation:

1. **Configuration**: Update config structure to match new format
2. **Service Factory**: Replace with `FaultTolerantAdapterManager`
3. **Health Routes**: Update to use new health monitoring endpoints
4. **Tests**: Update test mocks to work with new architecture

See [Migration Guide](migration_to_fault_tolerance.md) for detailed steps.

## Troubleshooting

### Common Issues

#### Adapters Still Blocking
- Verify `fault_tolerance.enabled: true`
- Check that adapters are using async/await properly
- Ensure no synchronous I/O in adapter code

#### Circuit Breakers Not Opening
- Check failure threshold configuration
- Verify error types are being recorded
- Look for exception handling that prevents failure recording

#### Poor Performance
- Review timeout settings
- Check concurrency limits
- Monitor resource usage (CPU, memory)
- Verify adapters aren't doing blocking operations

#### Inconsistent Behavior
- Check for shared state between adapters
- Verify configuration isn't being modified at runtime
- Look for race conditions in adapter initialization

### Debug Mode

Enable detailed logging:

```yaml
logging:
  level: DEBUG
  
fault_tolerance:
  debug_mode: true  # Additional debugging info
```

This provides detailed execution timing, circuit state changes, and error context.