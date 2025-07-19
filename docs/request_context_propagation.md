# Request Context Propagation

## Overview

The `ParallelAdapterExecutor` now supports request context propagation, enabling better tracing, logging, and debugging across parallel adapter execution. This feature allows you to track requests through the entire execution pipeline and correlate logs and results.

## Key Features

### 1. AdapterExecutionContext

A new dataclass that encapsulates request context information:

```python
@dataclass
class AdapterExecutionContext:
    request_id: str                    # Unique request identifier
    user_id: Optional[str] = None      # User making the request
    api_key: Optional[str] = None      # API key used
    trace_id: Optional[str] = None     # Distributed tracing ID
    session_id: Optional[str] = None   # User session ID
    correlation_id: Optional[str] = None # Business correlation ID
```

### 2. Automatic Context Generation

If no context is provided, the executor automatically generates one:

```python
# Auto-generates context with UUID request_id
results = await executor.execute_adapters(
    query="test query",
    adapter_names=["adapter1", "adapter2"]
)
```

### 3. Explicit Context Usage

Provide your own context for full control:

```python
context = AdapterExecutionContext(
    request_id="req-12345",
    user_id="user-67890",
    trace_id="trace-abc123",
    session_id="session-def456"
)

results = await executor.execute_adapters(
    query="test query",
    adapter_names=["adapter1", "adapter2"],
    context=context
)
```

## Context Propagation Flow

### 1. Logging with Context

All log messages include context information:

```
[req-12345] trace:trace-abc123 user:user-67890 Executing 2 adapters: ['adapter1', 'adapter2']
[req-12345] trace:trace-abc123 user:user-67890 Starting execution of adapter adapter1 (timeout: 10.0s)
[req-12345] trace:trace-abc123 user:user-67890 Adapter adapter1 completed successfully in 0.15s
```

### 2. Adapter Context Injection

Context information is automatically passed to adapters:

```python
# In your adapter's get_relevant_context method
async def get_relevant_context(self, query: str, **kwargs):
    request_id = kwargs.get('request_id')  # From context
    user_id = kwargs.get('user_id')        # From context
    trace_id = kwargs.get('trace_id')      # From context
    
    # Use context for logging, metrics, etc.
    logger.info(f"Processing request {request_id} for user {user_id}")
    
    return [{"content": "result", "request_id": request_id}]
```

### 3. Result Context Inclusion

Context information is included in results:

```python
result = AdapterResult(
    adapter_name="adapter1",
    success=True,
    data=[{"content": "result"}],
    execution_time=0.15,
    context=context  # Full context preserved
)
```

### 4. Combined Results with Context

When combining results, context information is preserved:

```python
combined = executor._combine_results(results)
# Each item includes:
# - request_id, user_id, trace_id, session_id, correlation_id
# - adapter_name, execution_time
# - original content
```

## Usage Examples

### Basic Usage

```python
from services.parallel_adapter_executor import (
    ParallelAdapterExecutor,
    AdapterExecutionContext
)

# Create executor
executor = ParallelAdapterExecutor(adapter_manager, config)

# Execute with auto-generated context
results = await executor.execute_adapters(
    query="What is the weather?",
    adapter_names=["weather-adapter", "location-adapter"]
)
```

### Advanced Usage with Tracing

```python
import uuid

# Create context with tracing information
context = AdapterExecutionContext(
    request_id=str(uuid.uuid4()),
    user_id="user-12345",
    trace_id="trace-67890",
    session_id="session-abc123",
    correlation_id="corr-def456"
)

# Execute with context
results = await executor.execute_adapters(
    query="Complex query",
    adapter_names=["adapter1", "adapter2", "adapter3"],
    context=context
)

# Results include full context
for result in results:
    print(f"Adapter: {result.adapter_name}")
    print(f"Request ID: {result.context.request_id}")
    print(f"User ID: {result.context.user_id}")
    print(f"Trace ID: {result.context.trace_id}")
```

### Integration with Distributed Tracing

```python
# With OpenTelemetry or similar
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("adapter_execution") as span:
    # Extract trace context
    trace_id = format(span.get_span_context().trace_id, '032x')
    
    context = AdapterExecutionContext(
        request_id=str(uuid.uuid4()),
        trace_id=trace_id,
        user_id=user_id
    )
    
    results = await executor.execute_adapters(
        query=query,
        adapter_names=adapter_names,
        context=context
    )
```

## Benefits

### 1. **Improved Debugging**
- Track requests across multiple adapters
- Correlate logs with specific requests
- Identify performance bottlenecks per request

### 2. **Better Observability**
- Request-level metrics and monitoring
- User-specific analytics
- Session tracking and correlation

### 3. **Enhanced Logging**
- Structured logging with context
- Consistent log format across adapters
- Easy log aggregation and filtering

### 4. **Distributed Tracing Support**
- Integration with tracing systems (Jaeger, Zipkin, etc.)
- End-to-end request tracking
- Performance analysis across services

### 5. **Business Context**
- User session tracking
- Business correlation IDs
- Audit trail capabilities

## Configuration

The context propagation works with existing configuration and doesn't require additional settings. However, you can control logging verbosity:

```python
import logging

# Set log level to see context in logs
logging.getLogger('services.parallel_adapter_executor').setLevel(logging.INFO)
```

## Migration Guide

### Existing Code

```python
# Old way (still works)
results = await executor.execute_adapters(
    query="test",
    adapter_names=["adapter1"]
)
```

### Enhanced Code

```python
# New way with context
context = AdapterExecutionContext(
    request_id="req-123",
    user_id="user-456"
)

results = await executor.execute_adapters(
    query="test",
    adapter_names=["adapter1"],
    context=context
)
```

## Testing

Run the context propagation tests:

```bash
pytest ./server/tests/test_context_propagation.py -v
```

Run the example:

```bash
python3 examples/context_propagation_example.py
```

## Best Practices

1. **Always provide a request_id** for production systems
2. **Use trace_id** when integrating with distributed tracing
3. **Include user_id** for user-specific analytics
4. **Add correlation_id** for business process tracking
5. **Use session_id** for session-based features
6. **Log context information** in your adapters
7. **Preserve context** in your response handling

## Integration Points

### Adapter Integration

Update your adapters to use context information:

```python
class MyAdapter:
    async def get_relevant_context(self, query: str, **kwargs):
        request_id = kwargs.get('request_id')
        user_id = kwargs.get('user_id')
        
        # Use context for logging
        logger.info(f"Processing request {request_id} for user {user_id}")
        
        # Use context for metrics
        metrics.increment("adapter.calls", tags={"user_id": user_id})
        
        # Use context for caching
        cache_key = f"{request_id}:{query}"
        
        return [{"content": "result", "request_id": request_id}]
```

### API Integration

In your API endpoints:

```python
@app.post("/query")
async def query_endpoint(request: QueryRequest):
    # Extract context from request
    context = AdapterExecutionContext(
        request_id=request.request_id or str(uuid.uuid4()),
        user_id=request.user_id,
        trace_id=request.trace_id,
        session_id=request.session_id
    )
    
    # Execute with context
    results = await executor.execute_adapters(
        query=request.query,
        adapter_names=request.adapters,
        context=context
    )
    
    # Return results with context
    return {
        "request_id": context.request_id,
        "results": executor._combine_results(results)
    }
```

This context propagation system provides a solid foundation for observability, debugging, and tracing in your parallel adapter execution pipeline. 