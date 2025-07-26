# ORBIT Inference Architecture Redesign

## Current Problems

The current inference architecture suffers from several design issues:

1. **Constructor Dependency Hell**: LLM clients receive 5+ service dependencies
2. **Single Responsibility Violation**: LLM clients handle inference, retrieval, safety, reranking, prompts
3. **Tight Coupling**: Direct service-to-service calls (`self.retriever.get_relevant_context()`)
4. **Hard to Test**: Mocking multiple services for unit tests is complex
5. **Difficult Extension**: Adding new services requires updating all client constructors

## Proposed Solution: Pipeline Architecture + Dependency Injection

### 1. Pipeline-Based Processing

Replace the monolithic LLM client approach with a composable pipeline:

```python
# Example pipeline flow:
Request -> [SafetyFilter] -> [ContextRetriever] -> [Reranker] -> [LLMInference] -> [ResponseFormatter] -> Response
```

### 2. Service Container for Dependency Injection

```python
from typing import Dict, Any, Type, Optional
from abc import ABC, abstractmethod

class ServiceContainer:
    """Dependency injection container for managing services."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
        self._singletons: Dict[str, Any] = {}
    
    def register_singleton(self, name: str, instance: Any) -> None:
        """Register a singleton service instance."""
        self._singletons[name] = instance
    
    def register_factory(self, name: str, factory: callable) -> None:
        """Register a factory function for service creation."""
        self._factories[name] = factory
    
    def get(self, name: str) -> Any:
        """Get a service by name."""
        # Check singletons first
        if name in self._singletons:
            return self._singletons[name]
        
        # Create from factory
        if name in self._factories:
            service = self._factories[name]()
            return service
        
        raise KeyError(f"Service '{name}' not found")
    
    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._singletons or name in self._factories
```

### 3. Pipeline Step Interface

```python
class PipelineStep(ABC):
    """Base interface for pipeline steps."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
    
    @abstractmethod
    async def process(self, context: "ProcessingContext") -> "ProcessingContext":
        """Process the context and return modified context."""
        pass
    
    @abstractmethod
    def should_execute(self, context: "ProcessingContext") -> bool:
        """Determine if this step should execute based on context."""
        pass

class ProcessingContext:
    """Shared context passed through pipeline steps."""
    
    def __init__(self):
        self.message: str = ""
        self.collection_name: str = ""
        self.system_prompt_id: Optional[str] = None
        self.context_messages: List[Dict[str, str]] = []
        self.retrieved_docs: List[Dict[str, Any]] = []
        self.response: str = ""
        self.sources: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.is_blocked: bool = False
        self.error: Optional[str] = None
        self.config: Dict[str, Any] = {}
```

### 4. Concrete Pipeline Steps

```python
class SafetyFilterStep(PipelineStep):
    """Check message safety using guardrail service."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return self.container.has('guardrail_service')
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
            
        guardrail = self.container.get('guardrail_service')
        is_safe, refusal_message = await guardrail.check_safety(context.message)
        
        if not is_safe:
            context.is_blocked = True
            context.error = refusal_message or "Request blocked by safety filter"
        
        return context

class ContextRetrievalStep(PipelineStep):
    """Retrieve relevant context documents."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return (not context.config.get('inference_only', False) and 
                self.container.has('retriever') and 
                not context.is_blocked)
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
            
        retriever = self.container.get('retriever')
        docs = await retriever.get_relevant_context(
            query=context.message,
            collection_name=context.collection_name
        )
        context.retrieved_docs = docs
        return context

class RerankerStep(PipelineStep):
    """Rerank retrieved documents."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return (self.container.has('reranker_service') and 
                context.retrieved_docs and 
                not context.is_blocked)
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked or not context.retrieved_docs:
            return context
            
        reranker = self.container.get('reranker_service')
        context.retrieved_docs = await reranker.rerank(
            context.message, 
            context.retrieved_docs
        )
        return context

class LLMInferenceStep(PipelineStep):
    """Generate response using LLM."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return self.container.has('llm_provider') and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
            
        llm_provider = self.container.get('llm_provider')
        
        # Build prompt with context
        system_prompt = await self._get_system_prompt(context)
        formatted_context = self._format_context(context.retrieved_docs)
        full_prompt = self._build_prompt(
            context.message, 
            system_prompt, 
            formatted_context, 
            context.context_messages
        )
        
        # Generate response
        response = await llm_provider.generate(full_prompt)
        context.response = response
        
        return context
    
    async def _get_system_prompt(self, context: ProcessingContext) -> str:
        if self.container.has('prompt_service') and context.system_prompt_id:
            prompt_service = self.container.get('prompt_service')
            prompt_doc = await prompt_service.get_prompt_by_id(context.system_prompt_id)
            if prompt_doc:
                return prompt_doc.get('prompt', '')
        return "You are a helpful assistant."
    
    def _format_context(self, docs: List[Dict[str, Any]]) -> str:
        if not docs:
            return ""
        
        context = ""
        for i, doc in enumerate(docs):
            content = doc.get('content', '')
            source = doc.get('metadata', {}).get('source', f"Document {i+1}")
            context += f"[{i+1}] {source}\n{content}\n\n"
        
        return context
    
    def _build_prompt(self, message: str, system_prompt: str, 
                     context: str, history: List[Dict[str, str]]) -> str:
        parts = [system_prompt]
        
        if context:
            parts.append(f"\nContext:\n{context}")
        
        if history:
            parts.append("\nConversation History:")
            for msg in history:
                role = msg.get('role', '').lower()
                content = msg.get('content', '')
                if role and content:
                    parts.append(f"{role.title()}: {content}")
        
        parts.append(f"\nUser: {message}")
        parts.append("Assistant:")
        
        return "\n".join(parts)
```

### 5. Pipeline Orchestrator

```python
from typing import List, Type

class InferencePipeline:
    """Orchestrates the execution of pipeline steps."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.steps: List[PipelineStep] = []
    
    def add_step(self, step_class: Type[PipelineStep]) -> 'InferencePipeline':
        """Add a step to the pipeline."""
        step = step_class(self.container)
        self.steps.append(step)
        return self
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Execute all pipeline steps in sequence."""
        for step in self.steps:
            if step.should_execute(context):
                try:
                    context = await step.process(context)
                    if context.is_blocked or context.error:
                        break
                except Exception as e:
                    context.error = str(e)
                    context.is_blocked = True
                    break
        
        return context

class InferencePipelineBuilder:
    """Builder for creating inference pipelines."""
    
    @staticmethod
    def build_standard_pipeline(container: ServiceContainer) -> InferencePipeline:
        """Build the standard inference pipeline."""
        return (InferencePipeline(container)
                .add_step(SafetyFilterStep)
                .add_step(ContextRetrievalStep)
                .add_step(RerankerStep)
                .add_step(LLMInferenceStep))
    
    @staticmethod
    def build_inference_only_pipeline(container: ServiceContainer) -> InferencePipeline:
        """Build a pipeline for inference-only mode."""
        return (InferencePipeline(container)
                .add_step(SafetyFilterStep)
                .add_step(LLMInferenceStep))
```

### 6. Simplified LLM Providers

LLM providers now only handle the core inference:

```python
class LLMProvider(ABC):
    """Simple interface for LLM providers - only handles generation."""
    
    @abstractmethod
    async def initialize(self) -> None:
        pass
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate response for the given prompt."""
        pass
    
    @abstractmethod
    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Generate streaming response."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI implementation - focused only on generation."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = None
    
    async def initialize(self) -> None:
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=self.config['api_key'])
    
    async def generate(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.config['model'],
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.get('temperature', 0.1)
        )
        return response.choices[0].message.content
    
    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        # Implement streaming
        pass
    
    async def close(self) -> None:
        if self.client:
            await self.client.close()
```

### 7. New Chat Service

```python
class ChatService:
    """Simplified chat service using the pipeline architecture."""
    
    def __init__(self, pipeline: InferencePipeline, chat_history_service=None):
        self.pipeline = pipeline
        self.chat_history_service = chat_history_service
    
    async def process_chat(self, message: str, collection_name: str, 
                          system_prompt_id: Optional[str] = None,
                          session_id: Optional[str] = None,
                          user_id: Optional[str] = None,
                          api_key: Optional[str] = None) -> Dict[str, Any]:
        
        # Create processing context
        context = ProcessingContext()
        context.message = message
        context.collection_name = collection_name
        context.system_prompt_id = system_prompt_id
        
        # Add conversation history if available
        if session_id and self.chat_history_service:
            context.context_messages = await self.chat_history_service.get_context_messages(session_id)
        
        # Process through pipeline
        result = await self.pipeline.process(context)
        
        # Handle result
        if result.error:
            return {"error": result.error}
        
        # Store conversation if enabled
        if session_id and self.chat_history_service:
            await self.chat_history_service.add_conversation_turn(
                session_id=session_id,
                user_message=message,
                assistant_response=result.response,
                user_id=user_id,
                api_key=api_key
            )
        
        return {
            "response": result.response,
            "sources": result.sources,
            "metadata": result.metadata
        }
```

### 8. Service Initialization

```python
class ServiceFactory:
    """Factory for initializing services with dependency injection."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.container = ServiceContainer()
    
    async def initialize_services(self) -> ServiceContainer:
        """Initialize all services and register them in the container."""
        
        # Register configuration
        self.container.register_singleton('config', self.config)
        
        # Initialize and register services based on config
        if not self.config.get('general', {}).get('inference_only', False):
            await self._register_rag_services()
        
        await self._register_core_services()
        await self._register_llm_provider()
        
        return self.container
    
    async def _register_rag_services(self):
        """Register RAG-related services."""
        # MongoDB
        if self.config.get('database'):
            mongodb = await self._create_mongodb_service()
            self.container.register_singleton('mongodb_service', mongodb)
        
        # Retriever
        retriever = await self._create_retriever()
        self.container.register_singleton('retriever', retriever)
        
        # Prompt service
        prompt_service = await self._create_prompt_service()
        self.container.register_singleton('prompt_service', prompt_service)
        
        # Reranker (optional)
        if self.config.get('reranker', {}).get('enabled'):
            reranker = await self._create_reranker()
            self.container.register_singleton('reranker_service', reranker)
    
    async def _register_core_services(self):
        """Register core services."""
        # Guardrail service (optional)
        if self.config.get('guardrail', {}).get('enabled'):
            guardrail = await self._create_guardrail()
            self.container.register_singleton('guardrail_service', guardrail)
        
        # Logger service
        logger_service = await self._create_logger()
        self.container.register_singleton('logger_service', logger_service)
    
    async def _register_llm_provider(self):
        """Register LLM provider."""
        provider_name = self.config['general']['inference_provider']
        provider = await self._create_llm_provider(provider_name)
        self.container.register_singleton('llm_provider', provider)
```

## Benefits of New Architecture

### 1. **Separation of Concerns**
- Each pipeline step has a single responsibility
- LLM providers only handle inference
- Services are loosely coupled

### 2. **Easy Testing**
```python
# Test individual steps
context = ProcessingContext()
context.message = "test"
step = SafetyFilterStep(mock_container)
result = await step.process(context)

# Test with mocked services
mock_container = ServiceContainer()
mock_container.register_singleton('guardrail_service', mock_guardrail)
```

### 3. **Flexible Extension**
```python
# Add new step easily
class CustomProcessingStep(PipelineStep):
    async def process(self, context):
        # Custom logic
        return context

# Add to pipeline
pipeline.add_step(CustomProcessingStep)
```

### 4. **Configuration-Driven**
- Steps self-determine if they should execute
- Easy to enable/disable features
- No hard dependencies in constructors

### 5. **Better Error Handling**
- Errors stop pipeline gracefully
- Each step can handle its own errors
- Clear error propagation

## Further Considerations

Based on a review of the current system, two additional areas should be addressed in the new architecture:

### 1. Streaming Response Handling

The current `InferencePipeline.process` method is designed for unary request/response interactions. To fully support streaming, the pipeline orchestration logic will need to be adapted.

- The `InferencePipeline` will require a new method, such as `process_stream`, that can handle `AsyncGenerator`s.
- The `LLMInferenceStep` will need a corresponding `process_stream` method that calls the `llm_provider.generate_stream()` method and yields context updates.
- The `ChatService` will need to be updated to call the appropriate pipeline processing method based on whether a streaming response is requested.

### 2. Output/Response Security Scanning

The current `SafetyFilterStep` only validates the incoming user message. The existing `LLMClientCommon` also performs security checks on the *outgoing* LLM response. This functionality must be preserved.

A new `ResponseValidationStep` should be added to the pipeline after the `LLMInferenceStep` to validate the generated `context.response`.

```python
class ResponseValidationStep(PipelineStep):
    """Perform safety check on the final generated response."""

    def should_execute(self, context: ProcessingContext) -> bool:
        return self.container.has('guardrail_service') and not context.is_blocked

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked or not context.response:
            return context

        guardrail = self.container.get('guardrail_service')
        is_safe, refusal_message = await guardrail.check_safety(context.response)

        if not is_safe:
            context.is_blocked = True
            context.error = refusal_message or "Response blocked by safety filter"
            context.response = ""  # Clear the unsafe response

        return context

# Updated standard pipeline
def build_standard_pipeline(container: ServiceContainer) -> InferencePipeline:
    """Build the standard inference pipeline."""
    return (InferencePipeline(container)
            .add_step(SafetyFilterStep)
            .add_step(ContextRetrievalStep)
            .add_step(RerankerStep)
            .add_step(LLMInferenceStep)
            .add_step(ResponseValidationStep))
```

## Migration Strategy

1. **Phase 1**: Implement new architecture alongside existing
2. **Phase 2**: Create adapter layer for backward compatibility
3. **Phase 3**: Migrate existing LLM clients to new providers
4. **Phase 4**: Remove old architecture