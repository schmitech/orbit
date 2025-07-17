# Fault Tolerance Troubleshooting Guide

This guide helps diagnose and resolve common issues with ORBIT's fault tolerance system, including circuit breaker problems, performance issues, and configuration errors.

## Common Issues and Solutions

### 1. Circuit Breakers Not Opening

**Symptoms:**
- Failing adapters continue to be called
- No "Circuit breaker OPENED" log messages
- High error rates persist

**Diagnosis:**
```bash
# Check circuit breaker status
curl http://localhost:3000/health/adapters

# Look for failure patterns in logs
grep "Error in adapter" logs/orbit.log | tail -20

# Check configuration
grep -A 10 "fault_tolerance" config/config.yaml
```

**Solutions:**

1. **Verify failure threshold configuration:**
```yaml
fault_tolerance:
  failure_threshold: 5  # Make sure this is reasonable (3-10)
```

2. **Check error handling in adapters:**
```python
# BAD: Catching all exceptions prevents failure recording
try:
    result = await external_service.call()
    return result
except Exception:
    return []  # This prevents circuit breaker from seeing failures

# GOOD: Let exceptions propagate or record failures explicitly
try:
    result = await external_service.call()
    return result
except SpecificException as e:
    logger.error(f"Adapter {self.name} failed: {e}")
    raise  # Let circuit breaker handle it
```

3. **Enable debug logging:**
```yaml
logging:
  level: DEBUG
  
fault_tolerance:
  circuit_breaker:
    enable_metrics: true
```

### 2. Adapters Still Blocking

**Symptoms:**
- Request timeouts
- Multiple adapters taking sequential time instead of parallel
- Thread pool exhaustion errors

**Diagnosis:**
```bash
# Check if fault tolerance is enabled
grep "Fault tolerance enabled" logs/orbit.log

# Look for blocking operations
grep "blocking" logs/orbit.log

# Check thread usage
ps -M <pid> | grep orbit  # On macOS
cat /proc/<pid>/status | grep Threads  # On Linux
```

**Solutions:**

1. **Verify fault tolerance is enabled:**
```yaml
fault_tolerance:
  enabled: true  # Must be explicitly true
```

2. **Check for synchronous I/O in adapters:**
```python
# BAD: Synchronous database calls
def get_relevant_context(self, query):
    conn = pymongo.MongoClient()  # Blocking!
    results = conn.db.collection.find({"query": query})
    return list(results)

# GOOD: Async database calls
async def get_relevant_context(self, query):
    conn = motor.motor_asyncio.AsyncIOMotorClient()
    results = await conn.db.collection.find({"query": query}).to_list(100)
    return results
```

3. **Wrap synchronous code in thread executor:**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class MyAdapter:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def get_relevant_context(self, query):
        # Run blocking code in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor, 
            self._sync_operation, 
            query
        )
        return result
    
    def _sync_operation(self, query):
        # Synchronous code here
        return process_query(query)
```

### 3. Timeouts Not Working

**Symptoms:**
- Adapters run longer than configured timeout
- No timeout log messages
- Slow adapters never fail

**Diagnosis:**
```bash
# Check timeout configuration
grep -A 5 "execution:" config/config.yaml

# Look for timeout messages
grep "Timeout for adapter" logs/orbit.log

# Check actual execution times
grep "execution_time" logs/orbit.log | tail -10
```

**Solutions:**

1. **Verify timeout configuration:**
```yaml
fault_tolerance:
  execution:
    timeout: 30.0  # Total timeout per adapter
    
  circuit_breaker:
    timeout: 30.0  # Alternative configuration location
```

2. **Check timeout allocation:**
```python
# Timeout is split: 30% initialization, 70% execution
total_timeout = 30.0
init_timeout = total_timeout * 0.3  # 9 seconds
exec_timeout = total_timeout * 0.7  # 21 seconds
```

3. **Ensure proper async/await usage:**
```python
# BAD: timeout doesn't work with blocking calls
async def get_relevant_context(self, query):
    time.sleep(60)  # This ignores asyncio.wait_for timeout!
    return results

# GOOD: Use async sleep or proper async calls
async def get_relevant_context(self, query):
    await asyncio.sleep(60)  # This respects timeout
    return results
```

### 4. Poor Performance

**Symptoms:**
- Slower response times than expected
- High CPU or memory usage
- Reduced throughput

**Diagnosis:**
```bash
# Check concurrent execution
grep "max_concurrent_adapters" config/config.yaml

# Monitor resource usage
top -p $(pgrep -f orbit)

# Check execution strategy
grep "strategy" config/config.yaml

# Look for thread pool issues
grep "ThreadPoolExecutor" logs/orbit.log
```

**Solutions:**

1. **Optimize concurrency settings:**
```yaml
fault_tolerance:
  execution:
    max_concurrent_adapters: 8  # Adjust based on CPU cores
    strategy: "first_success"   # For speed over completeness
```

2. **Tune timeout values:**
```yaml
fault_tolerance:
  execution:
    timeout: 10.0  # Reduce for faster failing
    
  circuit_breaker:
    failure_threshold: 3  # Fail faster
    recovery_timeout: 30.0  # Reduce recovery time
```

3. **Profile adapter performance:**
```python
import time
import logging

class ProfilingAdapter:
    async def get_relevant_context(self, query):
        start_time = time.time()
        try:
            result = await self._actual_query(query)
            execution_time = time.time() - start_time
            logging.info(f"Adapter {self.name} completed in {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logging.error(f"Adapter {self.name} failed after {execution_time:.2f}s: {e}")
            raise
```

### 5. Circuit Breakers Not Recovering

**Symptoms:**
- Circuits remain open permanently
- No "Circuit breaker CLOSED" messages
- Healthy adapters not being retried

**Diagnosis:**
```bash
# Check recovery timeout
grep "recovery_timeout" config/config.yaml

# Look for half-open transitions
grep "HALF_OPEN" logs/orbit.log

# Check success threshold
grep "success_threshold" config/config.yaml
```

**Solutions:**

1. **Verify recovery settings:**
```yaml
fault_tolerance:
  recovery_timeout: 60.0     # Time before trying half-open
  success_threshold: 3       # Successes needed to close
```

2. **Test adapter recovery manually:**
```bash
# Reset circuit breaker
curl -X POST http://localhost:3000/health/adapters/my-adapter/reset

# Check if adapter works
curl http://localhost:3000/api/query -d '{"query": "test", "adapter_names": ["my-adapter"]}'
```

3. **Monitor half-open behavior:**
```python
# Add detailed logging to circuit breaker
def record_success(self):
    super().record_success()
    if self.state == CircuitState.HALF_OPEN:
        logger.info(f"Half-open success {self.stats.consecutive_successes}/{self.success_threshold} for {self.adapter_name}")
```

## Configuration Issues

### 1. Invalid Configuration Structure

**Error Messages:**
```
KeyError: 'fault_tolerance'
AttributeError: 'NoneType' object has no attribute 'get'
```

**Solution:**
Ensure proper configuration structure:
```yaml
fault_tolerance:
  enabled: true
  failure_threshold: 5
  recovery_timeout: 60.0
  success_threshold: 3
  
  # New nested structure
  execution:
    strategy: "all"
    timeout: 30.0
    max_concurrent_adapters: 10
    
  circuit_breaker:
    enable_metrics: true
    
  health_monitoring:
    enabled: true
    check_interval: 30.0
```

### 2. Environment Variable Override Issues

**Problem:** Configuration not being overridden by environment variables

**Solution:**
```bash
# Set environment variables
export ORBIT_FAULT_TOLERANCE_ENABLED=true
export ORBIT_FAULT_TOLERANCE_EXECUTION_TIMEOUT=45.0

# Check if variables are loaded
env | grep ORBIT_FAULT_TOLERANCE
```

### 3. Adapter-Specific Configuration

**Problem:** Some adapters need different settings

**Solution:**
```yaml
fault_tolerance:
  # Global defaults
  enabled: true
  failure_threshold: 5
  recovery_timeout: 60.0
  
  # Adapter-specific overrides
  adapters:
    slow-database-adapter:
      failure_threshold: 10
      recovery_timeout: 120.0
      execution:
        timeout: 60.0
        
    fast-api-adapter:
      failure_threshold: 3
      recovery_timeout: 30.0
      execution:
        timeout: 10.0
```

## Monitoring and Debugging

### 1. Enable Comprehensive Logging

```yaml
logging:
  level: DEBUG
  handlers:
    file:
      filename: logs/fault_tolerance.log
      level: DEBUG
      format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
```

### 2. Health Check Endpoints

```bash
# System health
curl http://localhost:3000/health/system

# Adapter health
curl http://localhost:3000/health/adapters

# Specific adapter
curl http://localhost:3000/health/adapters/my-adapter

# Circuit breaker stats
curl http://localhost:3000/health/adapters/my-adapter/stats
```

### 3. Metrics Collection

Set up monitoring with Prometheus:

```yaml
monitoring:
  prometheus:
    enabled: true
    port: 9090
    
fault_tolerance:
  circuit_breaker:
    enable_metrics: true
    metrics_window: 300.0  # 5 minutes
```

### 4. Debug Mode

Enable debug mode for detailed information:

```yaml
fault_tolerance:
  debug_mode: true  # Adds execution tracing
  
logging:
  loggers:
    services.parallel_adapter_executor:
      level: DEBUG
    services.fault_tolerant_adapter_manager:
      level: DEBUG
```

## Performance Tuning

### 1. Optimize for Speed

```yaml
fault_tolerance:
  execution:
    strategy: "first_success"    # Stop on first success
    timeout: 10.0                # Shorter timeout
    max_concurrent_adapters: 6   # Reduce concurrency
    
  circuit_breaker:
    failure_threshold: 3         # Fail faster
    recovery_timeout: 30.0       # Quick recovery
```

### 2. Optimize for Reliability

```yaml
fault_tolerance:
  execution:
    strategy: "all"              # Get all results
    timeout: 45.0                # Generous timeout
    max_concurrent_adapters: 12  # Higher concurrency
    
  circuit_breaker:
    failure_threshold: 8         # More tolerant
    recovery_timeout: 120.0      # Slower recovery
```

### 3. Optimize for Load

```yaml
fault_tolerance:
  execution:
    strategy: "best_effort"      # Balanced approach
    timeout: 20.0                # Moderate timeout
    max_concurrent_adapters: 15  # High concurrency
    
  circuit_breaker:
    failure_threshold: 5         # Standard threshold
    recovery_timeout: 60.0       # Standard recovery
```

## Testing and Validation

### 1. Test Circuit Breaker Behavior

```python
# Create a failing adapter for testing
class FailingTestAdapter:
    def __init__(self, failure_count=10):
        self.failure_count = failure_count
        self.calls = 0
    
    async def get_relevant_context(self, query):
        self.calls += 1
        if self.calls <= self.failure_count:
            raise Exception(f"Test failure {self.calls}")
        return [{"content": "success"}]

# Test circuit breaker opening
async def test_circuit_breaker():
    adapter = FailingTestAdapter(failure_count=5)
    
    # Should fail 5 times then circuit should open
    for i in range(10):
        try:
            result = await executor.execute_adapters(f"test {i}", ["failing-adapter"])
            print(f"Call {i}: {result}")
        except Exception as e:
            print(f"Call {i}: {e}")
        
        # Check circuit state
        cb = executor._get_circuit_breaker("failing-adapter")
        print(f"Circuit state: {cb.state}")
```

### 2. Load Testing

```bash
# Use wrk or similar tool
wrk -t4 -c100 -d30s --script=load_test.lua http://localhost:3000/api/query

# Monitor during load test
watch -n 1 'curl -s http://localhost:3000/health/adapters | jq'
```

### 3. Recovery Testing

```python
# Test adapter recovery
async def test_recovery():
    # 1. Break adapter
    adapter.break_connection()
    
    # 2. Trigger circuit breaker
    for _ in range(6):
        await executor.execute_adapters("test", ["test-adapter"])
    
    # 3. Fix adapter
    await asyncio.sleep(61)  # Wait for recovery timeout
    adapter.fix_connection()
    
    # 4. Test recovery
    result = await executor.execute_adapters("recovery test", ["test-adapter"])
    assert result[0].success
```

This troubleshooting guide should help identify and resolve most common issues with the fault tolerance system. For persistent problems, enable debug logging and examine the detailed execution flow.