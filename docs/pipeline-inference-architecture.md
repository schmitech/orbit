# Pipeline Inference Architecture - Technical Deep Dive

## Overview

ORBIT's pipeline inference architecture is a modern, composable system designed for processing AI inference requests through a series of discrete, testable steps. This document explains how the architecture works, its components, and the technical decisions behind its design.

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Architecture Components](#architecture-components)
3. [Request Flow](#request-flow)
4. [Pipeline Steps](#pipeline-steps)
5. [Service Container & Dependency Injection](#service-container--dependency-injection)
6. [Direct Providers](#direct-providers)
7. [Monitoring & Observability](#monitoring--observability)
8. [Configuration](#configuration)
9. [Error Handling](#error-handling)
10. [Performance Considerations](#performance-considerations)

## Core Concepts

### What is a Pipeline?

A **pipeline** is a sequence of processing steps that transform an input (user message) into an output (AI response). Each step has a single responsibility and can be independently tested, configured, and monitored. 

```
User Message → [Safety] → [Retrieval] → [Reranking] → [LLM] → [Validation] → Response
```

### Key Benefits

- **Modularity**: Each step is independent and replaceable
- **Testability**: Steps can be unit tested in isolation
- **Observability**: Per-step metrics and error tracking
- **Flexibility**: Steps can be enabled/disabled or reordered
- **Performance**: Direct provider implementations eliminate wrapper overhead

## Architecture Components

### 1. Processing Context

The `ProcessingContext` is a data container that flows through the pipeline, accumulating information at each step:

```python
@dataclass
class ProcessingContext:
    message: str = ""                    # Original user message
    collection_name: str = ""            # Vector DB collection to search
    retrieved_docs: List[Dict] = []      # Documents from RAG retrieval
    reranked_docs: List[Dict] = []       # Reranked relevant documents
    response: str = ""                   # Final AI response
    is_blocked: bool = False             # Safety check result
    error: Optional[str] = None          # Error information
    metadata: Dict[str, Any] = {}        # Step-specific metadata
```

### 2. Pipeline Steps

Each step implements the `PipelineStep` interface:

```python
class PipelineStep:
    def should_execute(self, context: ProcessingContext) -> bool:
        """Determine if this step should run based on context"""
        return True
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process the context and return modified context"""
        raise NotImplementedError
    
    def get_name(self) -> str:
        """Return human-readable step name for logging"""
        return self.__class__.__name__
```

### 3. Inference Pipeline

The `InferencePipeline` orchestrates step execution:

```python
class InferencePipeline:
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.steps: List[PipelineStep] = []
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Execute all steps in sequence, stopping on errors"""
        for step in self.steps:
            if context.has_error():
                break
            
            if step.should_execute(context):
                context = await step.process(context)
        
        return context
```

## Request Flow

Here's how a typical request flows through the pipeline:

### 1. Request Reception
```python
# FastAPI endpoint receives request
POST /v1/chat
{
    "message": "What is quantum computing?",
    "collection_name": "tech_docs"
}
```

### 2. Context Creation
```python
context = ProcessingContext(
    message="What is quantum computing?",
    collection_name="tech_docs"
)
```

### 3. Pipeline Execution

#### Step 1: Safety Filter
```python
class SafetyFilterStep(PipelineStep):
    async def process(self, context):
        # Check for harmful content, prompt injection, etc.
        if self.is_harmful(context.message):
            context.is_blocked = True
            context.error = "Content blocked by safety filter"
        return context
```

#### Step 2: Context Retrieval (RAG)
```python
class ContextRetrievalStep(PipelineStep):
    async def process(self, context):
        if context.collection_name:
            retriever = self.container.get('retriever')
            docs = await retriever.get_relevant_context(
                query=context.message,
                collection_name=context.collection_name
            )
            context.retrieved_docs = docs
        return context
```

#### Step 3: Reranking
```python
class RerankerStep(PipelineStep):
    async def process(self, context):
        if context.retrieved_docs:
            reranker = self.container.get('reranker_service')
            ranked_docs = await reranker.rerank(
                query=context.message,
                documents=context.retrieved_docs
            )
            context.reranked_docs = ranked_docs
        return context
```

#### Step 4: LLM Inference
```python
class LLMInferenceStep(PipelineStep):
    async def process(self, context):
        llm_provider = self.container.get('llm_provider')
        
        # Build prompt with context
        prompt = self.build_prompt(context.message, context.reranked_docs)
        
        # Generate response
        context.response = await llm_provider.generate(prompt)
        return context
```

#### Step 5: Response Validation
```python
class ResponseValidationStep(PipelineStep):
    async def process(self, context):
        # Check response for safety, relevance, etc.
        if self.is_response_invalid(context.response):
            context.error = "Response failed validation"
        return context
```

### 4. Response Return
```python
{
    "response": "Quantum computing is a type of computation...",
    "metadata": {
        "retrieved_docs": 5,
        "processing_time_ms": 234
    }
}
```

## Pipeline Steps

### Built-in Steps

1. **SafetyFilterStep**: Input validation and content filtering
2. **ContextRetrievalStep**: RAG document retrieval from vector databases
3. **RerankerStep**: Relevance-based document reranking
4. **LLMInferenceStep**: Language model text generation
5. **ResponseValidationStep**: Output safety and quality checks

### Step Configuration

Each step can be configured independently:

```yaml
pipeline:
  steps:
    safety_filter:
      enabled: true
      timeout_ms: 1000
    
    context_retrieval:
      enabled: true
      timeout_ms: 3000
      max_documents: 10
    
    llm_inference:
      enabled: true
      timeout_ms: 30000
```

### Custom Steps

You can create custom steps by implementing `PipelineStep`:

```python
class CustomAnalyticsStep(PipelineStep):
    def should_execute(self, context):
        # Only run for certain collections
        return context.collection_name == "analytics_data"
    
    async def process(self, context):
        # Custom processing logic
        analytics_service = self.container.get('analytics_service')
        insights = await analytics_service.analyze(context.message)
        context.metadata['insights'] = insights
        return context
```

## Service Container & Dependency Injection

The pipeline uses dependency injection to manage services and promote testability.

### Service Registration

```python
# Service registration at startup
container = ServiceContainer()

# Singleton services (shared instances)
container.register_singleton('config', app_config)
container.register_singleton('llm_provider', openai_provider)

# Factory services (new instance each time)
container.register_factory('temp_processor', lambda: TempProcessor())

# Service retrieval in steps
class MyStep(PipelineStep):
    async def process(self, context):
        llm = self.container.get('llm_provider')
        result = await llm.generate("prompt")
        return context
```

### Benefits

- **Loose Coupling**: Steps don't directly instantiate dependencies
- **Testability**: Easy to mock services for unit tests
- **Configuration**: Services configured once, used everywhere
- **Lifecycle Management**: Proper cleanup and resource management

## Direct Providers

ORBIT uses "direct providers" - native implementations that communicate directly with AI service APIs without wrapper layers.

### Provider Interface

```python
class LLMProvider:
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text response"""
        raise NotImplementedError
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response"""
        raise NotImplementedError
    
    async def validate_config(self) -> bool:
        """Validate provider configuration"""
        return True
```

### OpenAI Provider Example

```python
class OpenAIProvider(LLMProvider):
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config["inference"]["openai"]["api_key"]
        self.model = config["inference"]["openai"]["model"]
        self.client = AsyncOpenAI(api_key=self.api_key)
    
    async def generate(self, prompt: str, **kwargs) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.choices[0].message.content
    
    async def generate_stream(self, prompt: str, **kwargs):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            **kwargs
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

### Provider Benefits

- **Performance**: Direct API communication, no wrapper overhead
- **Streaming**: True streaming without buffering
- **Features**: Access to provider-specific features
- **Maintenance**: Fewer abstraction layers to maintain

## Monitoring & Observability

The pipeline includes comprehensive monitoring capabilities.

### Metrics Collection

```python
class PipelineMonitor:
    def record_step_execution(
        self,
        step_name: str,
        execution_time: float,
        success: bool,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        # Record execution metrics
        pass
    
    def get_step_metrics(self, step_name: str) -> AggregatedMetrics:
        # Return aggregated metrics for a step
        pass
    
    def get_health_status(self) -> Dict[str, Any]:
        # Return overall system health
        pass
```

### Health Monitoring

```python
# Health check endpoint
GET /v1/pipeline/health
{
    "status": "healthy",
    "pipeline_steps": ["SafetyFilterStep", "ContextRetrievalStep", "LLMInferenceStep"],
    "step_count": 3,
    "monitoring": {
        "overall_success_rate": 0.95,
        "avg_response_time": 1.2
    }
}
```

### Metrics Export

```python
# JSON metrics
GET /v1/pipeline/metrics
{
    "SafetyFilterStep": {
        "total_executions": 1000,
        "success_rate": 0.99,
        "avg_execution_time": 0.05
    }
}

# Prometheus metrics
GET /v1/pipeline/metrics?format=prometheus
# HELP pipeline_step_executions_total Total step executions
pipeline_step_executions_total{step="SafetyFilterStep"} 1000
```

## Configuration

### Pipeline Configuration

```yaml
pipeline:
  # Use direct provider implementations for better performance
  use_direct_providers: true
  
  # Enable performance metrics logging
  log_metrics: true
  
  # Step-specific configuration
  steps:
    safety_filter:
      enabled: true
      timeout_ms: 1000
    
    context_retrieval:
      enabled: true
      timeout_ms: 3000
      max_documents: 10
    
    reranker:
      enabled: true
      timeout_ms: 2000
      top_k: 5
    
    llm_inference:
      enabled: true
      timeout_ms: 30000
    
    response_validation:
      enabled: true
      timeout_ms: 1000
  
  # Performance tuning
  performance:
    total_timeout_ms: 60000
    connection_pool_size: 10
  
  # Health monitoring
  monitoring:
    health_check:
      enabled: true
      interval_seconds: 30
      failure_threshold: 3
```

### Provider Configuration

```yaml
# LLM Provider configuration
inference:
  openai:
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-4"
    temperature: 0.1
    max_tokens: 2000
  
  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-3-sonnet-20240229"
    max_tokens: 2000

# General settings
general:
  inference_provider: "openai"  # Which provider to use
  inference_only: true          # Skip RAG if true
```

## Error Handling

### Error Propagation

```python
class ProcessingContext:
    def has_error(self) -> bool:
        return self.error is not None or self.is_blocked
    
    def set_error(self, error: str, block: bool = True):
        self.error = error
        if block:
            self.is_blocked = True
```

### Pipeline Error Handling

```python
async def process(self, context: ProcessingContext) -> ProcessingContext:
    for step in self.steps:
        # Stop processing if there's an error
        if context.has_error():
            break
        
        try:
            if step.should_execute(context):
                context = await step.process(context)
        except Exception as e:
            # Log error and update context
            logger.error(f"Step {step.get_name()} failed: {str(e)}")
            context.set_error(f"Step {step.get_name()} failed: {str(e)}")
            break
    
    return context
```

### Error Response Format

```python
# Error response
{
    "error": "Step LLMInferenceStep failed: API rate limit exceeded",
    "error_code": "RATE_LIMIT_EXCEEDED",
    "step": "LLMInferenceStep",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

## Performance Considerations

### Async Processing

All pipeline steps are async to prevent blocking:

```python
async def process_request(message: str) -> str:
    context = ProcessingContext(message=message)
    
    # Non-blocking pipeline execution
    result = await pipeline.process(context)
    
    return result.response
```

### Connection Pooling

Direct providers use connection pooling:

```python
class OpenAIProvider:
    def __init__(self, config):
        # Connection pooling for better performance
        self.client = AsyncOpenAI(
            api_key=config["api_key"],
            max_retries=3,
            timeout=30.0
        )
```

### Streaming Support

Pipeline supports streaming responses:

```python
async def process_stream(self, context: ProcessingContext) -> AsyncGenerator[str, None]:
    # Execute non-streaming steps first
    for step in self.non_streaming_steps:
        context = await step.process(context)
    
    # Stream from LLM step
    llm_step = self.get_llm_step()
    async for chunk in llm_step.process_stream(context):
        yield chunk
```

### Caching (Future Feature)

```yaml
pipeline:
  cache:
    enabled: true
    ttl_seconds: 3600
    max_size_mb: 100
```

## Testing

### Unit Testing Steps

```python
class TestSafetyFilterStep:
    @pytest.mark.asyncio
    async def test_blocks_harmful_content(self):
        container = ServiceContainer()
        step = SafetyFilterStep(container)
        
        context = ProcessingContext(message="harmful content")
        result = await step.process(context)
        
        assert result.is_blocked
        assert "safety filter" in result.error.lower()
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_full_pipeline_flow():
    # Mock all services
    container = ServiceContainer()
    container.register_singleton('llm_provider', MockLLMProvider())
    
    # Create pipeline
    pipeline = InferencePipeline(container)
    pipeline.add_step(MockStep1)
    pipeline.add_step(MockStep2)
    
    # Test execution
    context = ProcessingContext(message="test")
    result = await pipeline.process(context)
    
    assert not result.has_error()
    assert result.response == "expected response"
```

## Migration from Legacy Systems

If you're migrating from a legacy inference system:

1. **Identify Current Steps**: Map existing logic to pipeline steps
2. **Create Custom Steps**: Implement `PipelineStep` for custom logic
3. **Configure Services**: Set up service container with dependencies
4. **Test Incrementally**: Test each step independently
5. **Monitor Performance**: Use built-in monitoring to compare performance

## Conclusion

ORBIT's pipeline inference architecture provides a robust, scalable, and maintainable foundation for AI inference workloads. Its modular design enables easy customization, comprehensive testing, and detailed observability while maintaining high performance through direct provider implementations.

The architecture scales from simple inference-only use cases to complex RAG pipelines with multiple processing steps, making it suitable for a wide range of AI applications.