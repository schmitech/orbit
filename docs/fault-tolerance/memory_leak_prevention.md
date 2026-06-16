# Memory Leak Prevention

## Overview

The `SimpleCircuitBreaker` now includes comprehensive memory leak prevention to ensure that circuit breaker statistics don't grow indefinitely and consume excessive memory over time. This feature automatically cleans up old historical data while preserving recent statistics for monitoring and debugging.

## Key Features

### 1. Time-Series Data Tracking

The circuit breaker now tracks detailed historical data with thread-safe operations:

```python
@dataclass
class CircuitBreakerStats:
    # ... existing counters ...
    
    # Time-series data for memory leak prevention
    call_history: List[Dict[str, Any]] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Max history size to cap list growth between cleanups (0 = unlimited)
    max_history_size: int = 10000
    max_transitions_size: int = 1000
    
    # Thread safety lock (not serialized)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
```

**Call History Records:**
- `timestamp`: When the call was made
- `success`: Whether the call succeeded
- `execution_time`: How long the call took

**State Transition Records:**
- `timestamp`: When the transition occurred
- `from_state`: Previous circuit state
- `to_state`: New circuit state
- `reason`: Why the transition happened

### 2. Thread Safety

All list operations on `call_history` and `state_transitions` are protected by a `threading.Lock` to prevent race conditions during concurrent adapter execution. This ensures data integrity when:
- Multiple coroutines record success/failure simultaneously
- Cleanup runs while new records are being added
- Status queries access history sizes

### 3. Automatic Cleanup

Circuit breakers automatically clean up old data based on configurable intervals:

```python
class SimpleCircuitBreaker:
    def __init__(self, adapter_name: str, 
                 cleanup_interval: float = 3600.0,    # 1 hour
                 retention_period: float = 86400.0,   # 24 hours
                 max_history_size: int = 10000,       # Max call history records
                 max_transitions_size: int = 1000):   # Max state transitions
        self.cleanup_interval = cleanup_interval
        self.retention_period = retention_period
        self.max_history_size = max_history_size
        self.max_transitions_size = max_transitions_size
        self._last_cleanup = time.time()
```

**Cleanup Process:**
- Runs automatically every `cleanup_interval` seconds
- Removes records older than `retention_period` seconds
- Enforces `max_history_size` and `max_transitions_size` caps on every record
- Uses in-place list filtering to reduce memory spike during cleanup
- Logs cleanup statistics for monitoring

### 4. Manual Cleanup

Force immediate cleanup when needed:

```python
# Force cleanup of a specific circuit breaker
cb.force_cleanup()

# Force cleanup of all circuit breakers
executor.force_cleanup_all_circuit_breakers()
```

### 5. Memory Usage Monitoring

Track memory usage across all circuit breakers:

```python
# Get memory usage summary
memory_summary = executor.get_memory_usage_summary()

# Example output:
{
    "total_call_history_records": 1250,
    "total_state_transition_records": 45,
    "total_memory_usage_estimate": 323750,  # bytes (~250 bytes per record)
    "by_adapter": {
        "qa-sql": {
            "call_history_size": 500,
            "state_transitions_size": 15,
            "max_history_size": 10000,
            "max_transitions_size": 1000,
            "last_cleanup": 1640995200.0,
            "cleanup_interval": 3600.0,
            "retention_period": 86400.0
        }
    }
}
```

## Configuration

### Global Settings

Configure default cleanup behavior in `config.yaml`:

```yaml
fault_tolerance:
  circuit_breaker:
    cleanup_interval: 3600.0      # Default: 1 hour
    retention_period: 86400.0     # Default: 24 hours
    max_history_size: 10000       # Default: 10000 call records max
    max_transitions_size: 1000    # Default: 1000 state transitions max
```

### Adapter-Specific Settings

Override defaults per adapter in `adapters.yaml`:

```yaml
adapters:
  - name: "qa-sql"
    fault_tolerance:
      # ... other settings ...
      cleanup_interval: 3600.0         # Clean up every hour
      retention_period: 86400.0        # Keep data for 24 hours
      max_history_size: 10000          # Max call records
      max_transitions_size: 1000       # Max state transitions
      
  - name: "qa-vector-chroma"
    fault_tolerance:
      # ... other settings ...
      cleanup_interval: 1800.0         # Clean up every 30 minutes
      retention_period: 43200.0        # Keep data for 12 hours
      max_history_size: 5000           # Lower max for high-traffic adapter
      max_transitions_size: 500        # Lower max for high-traffic adapter
```

## Usage Examples

### Basic Usage

```python
from services.parallel_adapter_executor import ParallelAdapterExecutor

# Create executor (uses default cleanup settings)
executor = ParallelAdapterExecutor(adapter_manager, config)

# Circuit breakers automatically clean up old data
# No additional code needed
```

### Custom Cleanup Settings

```python
# Create circuit breaker with custom cleanup settings
cb = SimpleCircuitBreaker(
    adapter_name="my-adapter",
    cleanup_interval=1800.0,      # Clean up every 30 minutes
    retention_period=43200.0,     # Keep data for 12 hours
    max_history_size=5000,        # Cap at 5000 call records
    max_transitions_size=500      # Cap at 500 state transitions
)
```

### Manual Cleanup

```python
# Force cleanup of specific circuit breaker
cb = executor._get_circuit_breaker("qa-sql")
cb.force_cleanup()

# Force cleanup of all circuit breakers
executor.force_cleanup_all_circuit_breakers()
```

### Memory Monitoring

```python
# Check memory usage
memory_info = executor.get_memory_usage_summary()
print(f"Total records: {memory_info['total_call_history_records']}")
print(f"Estimated memory: {memory_info['total_memory_usage_estimate']} bytes")

# Check specific adapter
adapter_info = memory_info['by_adapter']['qa-sql']
print(f"QA-SQL call history: {adapter_info['call_history_size']} records")
```

## Benefits

### 1. **Memory Efficiency**
- Prevents unbounded memory growth
- Automatically removes old data
- Configurable retention periods
- Hard caps on list sizes prevent runaway growth

### 2. **Thread Safety**
- All list operations are protected by locks
- Safe for concurrent adapter execution
- No race conditions during cleanup

### 3. **Performance Optimization**
- Reduces memory pressure
- Faster status queries
- Better garbage collection
- In-place list filtering reduces memory spikes

### 4. **Monitoring and Debugging**
- Preserves recent history for analysis
- Tracks state transitions over time
- Provides accurate memory usage estimates (~250 bytes/record)

### 5. **Operational Control**
- Manual cleanup when needed
- Configurable cleanup intervals
- Adapter-specific settings
- Configurable max sizes for fine-grained control

## Configuration Guidelines

### High-Traffic Adapters

For adapters with high call volumes:

```yaml
fault_tolerance:
  cleanup_interval: 1800.0      # Clean up every 30 minutes
  retention_period: 43200.0     # Keep data for 12 hours
  max_history_size: 5000        # Lower cap for high traffic
  max_transitions_size: 500     # Lower cap for high traffic
```

### Low-Traffic Adapters

For adapters with low call volumes:

```yaml
fault_tolerance:
  cleanup_interval: 7200.0      # Clean up every 2 hours
  retention_period: 172800.0    # Keep data for 48 hours
  max_history_size: 10000       # Standard cap
  max_transitions_size: 1000    # Standard cap
```

### Network Services

For external network services:

```yaml
fault_tolerance:
  cleanup_interval: 1800.0      # More frequent cleanup
  retention_period: 43200.0     # Shorter retention
  max_history_size: 5000        # Moderate cap
  max_transitions_size: 500     # Moderate cap
```

### Local Services

For local database operations:

```yaml
fault_tolerance:
  cleanup_interval: 3600.0      # Standard cleanup
  retention_period: 86400.0     # Standard retention
  max_history_size: 10000       # Standard cap
  max_transitions_size: 1000    # Standard cap
```

## Monitoring and Alerts

### Memory Usage Alerts

Monitor memory usage and set alerts:

```python
# Check if memory usage is high
memory_summary = executor.get_memory_usage_summary()
total_records = memory_summary['total_call_history_records']

if total_records > 10000:  # Alert threshold
    logger.warning(f"High memory usage: {total_records} records")
    # Force cleanup
    executor.force_cleanup_all_circuit_breakers()
```

### Cleanup Monitoring

Monitor cleanup effectiveness:

```python
# Check cleanup frequency
for adapter_name, info in memory_summary['by_adapter'].items():
    time_since_cleanup = time.time() - info['last_cleanup']
    if time_since_cleanup > info['cleanup_interval'] * 2:
        logger.warning(f"Cleanup overdue for {adapter_name}")
```

## Best Practices

### 1. **Configure Appropriately**
- Set cleanup intervals based on traffic volume
- Adjust retention periods based on debugging needs
- Monitor memory usage regularly

### 2. **Monitor Cleanup Effectiveness**
- Check cleanup logs for issues
- Monitor memory usage trends
- Set up alerts for high memory usage

### 3. **Use Manual Cleanup Sparingly**
- Let automatic cleanup handle most cases
- Use manual cleanup for maintenance windows
- Monitor cleanup impact on performance

### 4. **Balance History vs Memory**
- Keep enough history for debugging
- Don't keep more data than needed
- Adjust settings based on operational needs

## Troubleshooting

### High Memory Usage

If memory usage is high:

1. **Check cleanup settings:**
   ```python
   memory_summary = executor.get_memory_usage_summary()
   print(memory_summary)
   ```

2. **Force cleanup:**
   ```python
   executor.force_cleanup_all_circuit_breakers()
   ```

3. **Adjust settings:**
   ```yaml
   fault_tolerance:
     cleanup_interval: 1800.0      # More frequent
     retention_period: 21600.0     # Shorter retention
     max_history_size: 5000        # Lower cap
     max_transitions_size: 500     # Lower cap
   ```

### Cleanup Not Working

If cleanup isn't working:

1. **Check logs for cleanup messages**
2. **Verify cleanup interval settings**
3. **Check if circuit breakers are being used**
4. **Force manual cleanup to test**
5. **Note:** Cleanup only triggers when adapters receive new traffic

### Performance Impact

If cleanup impacts performance:

1. **Increase cleanup interval**
2. **Reduce retention period**
3. **Lower max_history_size and max_transitions_size**
4. **Monitor cleanup timing**

## Technical Notes

### Thread Safety

All operations on `call_history` and `state_transitions` are protected by a `threading.Lock`:

```python
def add_call_record(self, timestamp: float, success: bool, execution_time: float = 0.0):
    """Add a call record to history (thread-safe)"""
    with self._lock:
        self.call_history.append({...})
        # Enforce max size cap
        if self.max_history_size > 0 and len(self.call_history) > self.max_history_size:
            self.call_history = self.call_history[-self.max_history_size:]
```

### Memory Estimation

Memory usage is estimated at ~250 bytes per record, which accounts for:
- Dictionary overhead
- String keys and values
- Float timestamps and execution times
- Python object overhead

### Max Size Enforcement

The `max_history_size` and `max_transitions_size` parameters provide a hard cap on list growth. When exceeded, the oldest records are discarded to maintain the cap. This prevents unbounded memory growth even between cleanup intervals.

This memory leak prevention system ensures that your circuit breakers remain efficient and don't consume excessive memory over time, while still providing valuable historical data for monitoring and debugging. 