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

Implements the circuit breaker pattern for individual adapters with memory leak prevention and event handling.

```python
class SimpleCircuitBreaker:
    def __init__(self, adapter_name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, success_threshold: int = 3,
                 max_recovery_timeout: float = 300.0, enable_exponential_backoff: bool = True,
                 cleanup_interval: float = 3600.0, retention_period: float = 86400.0,
                 event_handler: Optional[CircuitBreakerEventHandler] = None):
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self.event_handler = event_handler or DefaultCircuitBreakerEventHandler()
        
    def is_open(self) -> bool:
        if self.state == CircuitState.OPEN:
            # Check if we should transition to half-open
            if time.time() - self._state_changed_at >= self.current_recovery_timeout:
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
- OPEN → HALF_OPEN: After recovery timeout expires (with exponential backoff)
- HALF_OPEN → CLOSED: When success threshold is met
- HALF_OPEN → OPEN: On any failure during testing

**Enhanced Features:**
- **Exponential Backoff**: Recovery timeouts increase with consecutive failures
- **Memory Leak Prevention**: Automatic cleanup of old statistics
- **Event Handling**: Callbacks for monitoring and alerting systems
- **Context Propagation**: Request context tracking through execution pipeline

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
  recovery_timeout: 60.0        # Base seconds before trying half-open
  success_threshold: 3          # Successes to close circuit
  max_recovery_timeout: 300.0   # Maximum recovery timeout (exponential backoff)
  enable_exponential_backoff: true  # Enable exponential backoff
  
  # Memory leak prevention
  cleanup_interval: 3600.0      # Clean up stats every hour
  retention_period: 86400.0     # Keep stats for 24 hours
  
  # Execution settings
  execution:
    strategy: "all"             # "all", "first_success", "best_effort"
    timeout: 30.0               # Total timeout per adapter
    max_concurrent_adapters: 10 # Concurrent execution limit
    shutdown_timeout: 30.0      # Graceful shutdown timeout
  
  # Health monitoring
  health_monitoring:
    enabled: true
    check_interval: 30.0        # Health check frequency
    history_size: 100           # Number of recent calls to track
```

### Adapter-Specific Configuration

Each adapter can override global fault tolerance settings:

```yaml
adapters:
  - name: "qa-sql"
    fault_tolerance:
      operation_timeout: 15.0
      failure_threshold: 10
      recovery_timeout: 30.0
      success_threshold: 5
      max_recovery_timeout: 120.0
      enable_exponential_backoff: true
      cleanup_interval: 3600.0
      retention_period: 86400.0
      event_handler:
        type: "default"                # Use default filesystem logger
        # type: "monitoring"           # For monitoring systems
        # type: "custom"               # For custom handlers
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

Each circuit breaker tracks comprehensive statistics with memory leak prevention:

```python
@dataclass
class CircuitBreakerStats:
    failure_count: int = 0
    success_count: int = 0
    timeout_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    
    # Time-series data for memory leak prevention
    call_history: List[Dict[str, Any]] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
```

**Memory Management:**
- Automatic cleanup of old records based on `cleanup_interval`
- Configurable retention period via `retention_period`
- Manual cleanup available via `force_cleanup()`

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

# Get memory usage summary
GET /health/adapters/memory-usage

# Force cleanup of all circuit breakers
POST /health/adapters/cleanup
```

### Logging and Event Handling

The system provides structured logging and event handling for:

- Circuit state changes
- Adapter execution timing
- Timeout occurrences
- Error patterns
- Recovery events
- Memory cleanup operations
- Request context propagation

```python
logger.warning(f"Circuit breaker OPENED for adapter: {adapter_name}")
logger.info(f"Circuit breaker CLOSED for adapter: {adapter_name}")
logger.warning(f"Timeout for adapter {adapter_name} after {execution_time:.2f}s")
logger.debug(f"Circuit breaker cleanup for {adapter_name}: removed {cleaned} records")
```

**Event Handler Types:**

1. **Default Handler**: Logs events to filesystem
2. **Monitoring Handler**: Integrates with alerting and dashboard systems
3. **Custom Handler**: User-defined event processing logic

**Event Types:**
- `circuit_open`: Circuit opens due to failures
- `circuit_close`: Circuit closes after successful recovery
- `circuit_half_open`: Circuit transitions to testing state
- `circuit_reset`: Circuit is manually reset

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

- Circuit breaker stats: ~1KB per adapter (base)
- Time-series data: ~100 bytes per record (configurable retention)
- Memory leak prevention: Automatic cleanup prevents unbounded growth
- Parallel execution: Additional task overhead
- Thread pool: Configurable worker threads
- Graceful shutdown: Tracks active requests during shutdown

### Throughput

Concurrent request handling:

- Multiple requests can execute simultaneously
- Each request runs adapters in parallel
- Circuit breakers prevent resource waste on failing adapters

## Best Practices

### Configuration Guidelines

1. **Failure Threshold**: Start with 5, adjust based on adapter reliability
2. **Recovery Timeout**: 30-60 seconds for most use cases
3. **Max Recovery Timeout**: 300-600 seconds for exponential backoff
4. **Execution Timeout**: Based on acceptable response time (10-30s)
5. **Concurrency**: Start with 2x CPU cores, monitor resource usage
6. **Memory Management**: 
   - `cleanup_interval`: 1800-7200 seconds (30min-2hr)
   - `retention_period`: 43200-172800 seconds (12-48hr)
7. **Event Handling**: Use "default" for logging, "monitoring" for alerts

### Monitoring

1. Track circuit breaker state changes
2. Monitor timeout frequency by adapter
3. Set up alerts for high failure rates
4. Track response time distributions
5. Monitor memory usage and cleanup effectiveness
6. Track event handler performance and failures
7. Monitor graceful shutdown behavior
8. Track request context propagation

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
5. Test memory leak prevention and cleanup
6. Verify event handler callbacks and error handling
7. Test graceful shutdown with active requests
8. Validate request context propagation

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
- Check exponential backoff settings
- Verify event handler configuration

#### Poor Performance
- Review timeout settings
- Check concurrency limits
- Monitor resource usage (CPU, memory)
- Verify adapters aren't doing blocking operations
- Check memory usage and cleanup frequency
- Monitor event handler performance impact

#### Inconsistent Behavior
- Check for shared state between adapters
- Verify configuration isn't being modified at runtime
- Look for race conditions in adapter initialization
- Check for memory pressure affecting cleanup
- Verify event handler thread safety

### Debug Mode

Enable detailed logging:

```yaml
logging:
  level: DEBUG
  
fault_tolerance:
  debug_mode: true  # Additional debugging info
```

This provides detailed execution timing, circuit state changes, and error context.