# Performance Enhancements Implementation Guide

This guide explains the performance enhancements implemented based on the concurrency & performance roadmap.

## Implementation Status

✅ **Phase 1: Foundation Infrastructure** - COMPLETED
- Enhanced Thread Pool Management
- Advanced Connection Pool Configuration  
- Multi-Worker Uvicorn Configuration
- Specialized thread pools for different workload types

## Overview

The performance enhancements introduce specialized thread pools for different types of operations, improving concurrent request handling from ~50-100 to potentially 1000+ requests.

## Key Components

### 1. Thread Pool Manager

The `ThreadPoolManager` (`utils/thread_pool_manager.py`) provides centralized management of specialized thread pools:

- **IO Pool**: 50 workers for I/O-bound operations (file operations, network requests)
- **CPU Pool**: 30 workers for CPU-intensive tasks
- **Inference Pool**: 20 workers for model inference operations
- **Embedding Pool**: 15 workers for embedding generation
- **DB Pool**: 25 workers for database operations

### 2. Configuration

Added performance configuration section to `config.yaml`:

```yaml
performance:
  workers: 4                        # Number of uvicorn workers
  keep_alive_timeout: 30            # Uvicorn keep-alive timeout
  
  thread_pools:
    io_workers: 50              # Up from 10
    cpu_workers: 30             # CPU-bound tasks
    inference_workers: 20       # Model inference
    embedding_workers: 15       # Embedding generation
    db_workers: 25              # Database operations
```

### 3. Integration Points

#### InferenceServer Updates

The `InferenceServer` now:
- Initializes `ThreadPoolManager` instead of a single thread pool
- Stores it in `app.state` for service access
- Supports multi-worker uvicorn configuration
- Properly shuts down all thread pools on exit

#### Service Integration

Services can access the thread pool manager through `app.state.thread_pool_manager`.

## Usage Examples

### 1. Basic Usage in Services

```python
class MyService:
    def __init__(self, config, thread_pool_manager=None):
        self.config = config
        self.thread_pool_manager = thread_pool_manager
    
    async def process_data(self, data):
        if self.thread_pool_manager:
            # Use specialized pool for CPU-intensive work
            result = await self.thread_pool_manager.run_in_pool(
                'cpu',
                self._cpu_intensive_function,
                data
            )
        else:
            # Fallback to default executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._cpu_intensive_function, data)
        return result
```

### 2. Using with Keyword Arguments

The ThreadPoolManager supports functions with keyword arguments:

```python
# Functions with kwargs
async def task_with_options(data, multiplier=2, prefix="result"):
    processed = data * multiplier
    return f"{prefix}_{processed}"

# Using run_in_pool with kwargs
result = await thread_pool_manager.run_in_pool(
    'cpu',
    task_with_options,
    10,
    multiplier=3,
    prefix="test"
)
# Returns: "test_30"

# Using submit_to_pool with kwargs
future = thread_pool_manager.submit_to_pool(
    'io',
    task_with_options,
    5,
    prefix="async"
)
result = future.result()  # Returns: "async_10"
```

### 3. Batch Processing

```python
async def process_batch(self, items):
    async with self.thread_pool_manager.batch_executor('inference', max_concurrent=10) as submit:
        tasks = [submit(self.process_item, item) for item in items]
        results = await asyncio.gather(*tasks)
    return results
```

## Migration Guide

To update existing services:

1. **Add thread_pool_manager parameter**:
   ```python
   def __init__(self, config, ..., thread_pool_manager=None):
       self.thread_pool_manager = thread_pool_manager
   ```

2. **Update executor usage**:
   ```python
   # Old
   await loop.run_in_executor(None, func, *args)
   
   # New
   await self.thread_pool_manager.run_in_pool('appropriate_pool', func, *args)
   ```

3. **Choose appropriate pool**:
   - `'io'`: File operations, network requests
   - `'cpu'`: CPU-intensive computations
   - `'inference'`: Model inference
   - `'embedding'`: Embedding generation
   - `'db'`: Database operations

## Performance Monitoring

### Verbose Logging

When `general.verbose: true` is enabled in `config.yaml`, the ThreadPoolManager provides detailed logging:

- **Task Submission**: Logs when tasks are submitted to pools with current pool utilization
- **Task Completion**: Logs task completion times and success/failure status
- **Active Task Tracking**: Shows currently running tasks with duration
- **Pool Statistics**: Detailed worker utilization and queue status

Example verbose log output:
```
INFO ThreadPool[cpu] Task #42: Submitting 'process_data' (active_threads=2, queued=1)
INFO ThreadPool[cpu] Task #42: Completed in 0.150s
INFO ThreadPoolManager Current Status:
============================================================
  io           | Workers:   3/ 50 (  6.0%) | Queued:   0
  cpu          | Workers:   8/ 30 ( 26.7%) | Queued:   2
    └─ Task #45: heavy_computation (running for 1.2s)
  inference    | Workers:   1/ 20 (  5.0%) | Queued:   0
  embedding    | Workers:   0/ 15 (  0.0%) | Queued:   0
  db           | Workers:   2/ 25 (  8.0%) | Queued:   0
------------------------------------------------------------
  Total: 14 active threads, 2 queued tasks
============================================================
```

### HTTP Endpoints

When verbose mode is enabled, monitoring endpoints are available:

#### Get Thread Pool Statistics
```bash
# Get current thread pool stats as JSON  
curl http://localhost:3000/health/thread-pools

# Response:
{
  "summary": {
    "total_workers": 140,
    "total_active": 8,
    "total_queued": 2,
    "utilization_percent": 5.7
  },
  "pools": {
    "io": {
      "max_workers": 50,
      "active_threads": 3,
      "queued_tasks": 0,
      "active_tasks": [...]
    }
  }
}
```

#### Trigger Status Logging
```bash
# Trigger detailed status logging to server logs
curl -X POST http://localhost:3000/health/thread-pools/log-status
```

### Programmatic Monitoring

```python
# Get pool statistics
stats = thread_pool_manager.get_pool_stats()

# Log current status (verbose mode only)
thread_pool_manager.log_current_status()
```

## Best Practices

1. **Pool Selection**: Choose the appropriate pool based on operation type
2. **Fallback Support**: Always provide fallback for when thread_pool_manager is None
3. **Resource Limits**: Monitor memory usage with multiple model instances
4. **Graceful Degradation**: Handle pool exhaustion gracefully

## Testing

Comprehensive unit tests are available in `server/tests/test_thread_pool_manager.py`, covering:
- Basic initialization and configuration
- Pool retrieval and management
- Async/sync execution modes
- Keyword argument support
- High concurrency scenarios (100+ concurrent tasks)
- Mixed workload distribution across pools
- Pool saturation handling
- Error handling and partial failures
- Context manager usage
- Resource cleanup

Run tests with:
```bash
pytest server/tests/test_thread_pool_manager.py -v
```

## Performance Benchmarks

Based on the implementation:
- **Thread Pool Capacity**: 140 total workers (vs. 10 previously)
  - IO: 50 workers
  - CPU: 30 workers  
  - Inference: 20 workers
  - Embedding: 15 workers
  - DB: 25 workers
- **Multi-Worker Support**: 4 uvicorn workers by default
- **Expected Capacity**: 500-1000 concurrent requests (Phase 1 target)

## Future Enhancements

Based on the roadmap, future phases will add:

### Phase 2: Performance Optimization
- Request queue management
- Load balancing middleware
- Streaming response optimization
- Request batching system

### Phase 3: Enterprise Features  
- Multi-model pool management
- Real-time performance monitoring
- Auto-scaling logic
- ML-based demand prediction

## Troubleshooting

### High Memory Usage

If memory usage is high with multiple workers:
1. Reduce worker count in config
2. Monitor individual pool usage
3. Consider model quantization

### Pool Exhaustion

If a pool runs out of workers:
1. Check pool stats
2. Increase worker count for that pool
3. Implement request queuing

### Performance Testing

Test the improvements:
```bash
# Simple load test
ab -n 1000 -c 100 http://localhost:3000/health

# Monitor thread pools during load (requires verbose: true)
curl http://localhost:3000/health/thread-pools

# Watch thread pool utilization in real-time
watch -n 1 'curl -s http://localhost:3000/health/thread-pools | jq .summary'

# Trigger detailed logging during load testing
curl -X POST http://localhost:3000/health/thread-pools/log-status
```