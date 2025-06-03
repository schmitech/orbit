"""
Example implementation of the Pipeline Architecture for ORBIT Inference

This demonstrates how the new architecture eliminates tight coupling and provides
better extensibility compared to the current design.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator, Type
import asyncio
import logging

# ============================================================================
# Core Pipeline Infrastructure
# ============================================================================

class ServiceContainer:
    """Dependency injection container."""
    
    def __init__(self):
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
    
    def register_singleton(self, name: str, instance: Any) -> None:
        self._singletons[name] = instance
    
    def register_factory(self, name: str, factory: callable) -> None:
        self._factories[name] = factory
    
    def get(self, name: str) -> Any:
        if name in self._singletons:
            return self._singletons[name]
        if name in self._factories:
            return self._factories[name]()
        raise KeyError(f"Service '{name}' not found")
    
    def has(self, name: str) -> bool:
        return name in self._singletons or name in self._factories

class ProcessingContext:
    """Shared context for pipeline steps."""
    
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

class PipelineStep(ABC):
    """Base class for pipeline steps."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        pass
    
    @abstractmethod
    def should_execute(self, context: ProcessingContext) -> bool:
        pass

# ============================================================================
# Pipeline Steps Implementation
# ============================================================================

class SafetyFilterStep(PipelineStep):
    """Content safety filtering step."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return self.container.has('guardrail_service') and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
        
        guardrail = self.container.get('guardrail_service')
        is_safe, refusal_message = await guardrail.check_safety(context.message)
        
        if not is_safe:
            context.is_blocked = True
            context.error = refusal_message or "Content blocked by safety filter"
            self.logger.warning(f"Message blocked by safety filter: {context.message[:50]}...")
        
        return context

class ContextRetrievalStep(PipelineStep):
    """Document retrieval step."""
    
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
        self.logger.info(f"Retrieved {len(docs)} documents for query: {context.message[:50]}...")
        
        return context

class RerankerStep(PipelineStep):
    """Document reranking step."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return (self.container.has('reranker_service') and 
                context.retrieved_docs and 
                not context.is_blocked)
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked or not context.retrieved_docs:
            return context
        
        reranker = self.container.get('reranker_service')
        original_count = len(context.retrieved_docs)
        
        context.retrieved_docs = await reranker.rerank(
            context.message, 
            context.retrieved_docs
        )
        
        self.logger.info(f"Reranked {original_count} documents, kept {len(context.retrieved_docs)}")
        return context

class SystemPromptStep(PipelineStep):
    """System prompt resolution step."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return (context.system_prompt_id is not None and 
                self.container.has('prompt_service') and 
                not context.is_blocked)
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
        
        prompt_service = self.container.get('prompt_service')
        prompt_doc = await prompt_service.get_prompt_by_id(context.system_prompt_id)
        
        if prompt_doc and 'prompt' in prompt_doc:
            # Store in metadata for LLM step to use
            context.metadata['system_prompt'] = prompt_doc['prompt']
            self.logger.info(f"Loaded system prompt: {prompt_doc.get('name', 'Unknown')}")
        
        return context

class LLMInferenceStep(PipelineStep):
    """LLM inference step."""
    
    def should_execute(self, context: ProcessingContext) -> bool:
        return self.container.has('llm_provider') and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        if context.is_blocked:
            return context
        
        llm_provider = self.container.get('llm_provider')
        
        # Build prompt
        system_prompt = context.metadata.get('system_prompt', 'You are a helpful assistant.')
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
        
        # Format sources
        context.sources = self._format_sources(context.retrieved_docs)
        
        self.logger.info(f"Generated response of {len(response)} characters")
        return context
    
    def _format_context(self, docs: List[Dict[str, Any]]) -> str:
        if not docs:
            return ""
        
        context = ""
        for i, doc in enumerate(docs):
            content = doc.get('content', '')
            source = doc.get('metadata', {}).get('source', f"Document {i+1}")
            context += f"[{i+1}] {source}\n{content}\n\n"
        
        return context
    
    def _format_sources(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = []
        for i, doc in enumerate(docs):
            metadata = doc.get('metadata', {})
            sources.append({
                "id": i + 1,
                "title": metadata.get('title', f"Document {i+1}"),
                "source": metadata.get('source', ''),
                "confidence": doc.get('confidence', 0.0)
            })
        return sources
    
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

# ============================================================================
# Pipeline Orchestration
# ============================================================================

class InferencePipeline:
    """Pipeline orchestrator."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.steps: List[PipelineStep] = []
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def add_step(self, step_class: Type[PipelineStep]) -> 'InferencePipeline':
        step = step_class(self.container)
        self.steps.append(step)
        return self
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        self.logger.info(f"Processing pipeline with {len(self.steps)} steps")
        
        for i, step in enumerate(self.steps):
            if step.should_execute(context):
                try:
                    self.logger.debug(f"Executing step {i+1}: {step.__class__.__name__}")
                    context = await step.process(context)
                    
                    if context.is_blocked or context.error:
                        self.logger.warning(f"Pipeline stopped at step {i+1}: {step.__class__.__name__}")
                        break
                        
                except Exception as e:
                    self.logger.error(f"Error in step {i+1} ({step.__class__.__name__}): {str(e)}")
                    context.error = f"Pipeline error: {str(e)}"
                    context.is_blocked = True
                    break
            else:
                self.logger.debug(f"Skipping step {i+1}: {step.__class__.__name__}")
        
        return context

class InferencePipelineBuilder:
    """Builder for creating pipelines."""
    
    @staticmethod
    def build_standard_pipeline(container: ServiceContainer) -> InferencePipeline:
        """Build standard RAG pipeline."""
        return (InferencePipeline(container)
                .add_step(SafetyFilterStep)
                .add_step(SystemPromptStep)
                .add_step(ContextRetrievalStep)
                .add_step(RerankerStep)
                .add_step(LLMInferenceStep))
    
    @staticmethod
    def build_inference_only_pipeline(container: ServiceContainer) -> InferencePipeline:
        """Build inference-only pipeline."""
        return (InferencePipeline(container)
                .add_step(SafetyFilterStep)
                .add_step(SystemPromptStep)
                .add_step(LLMInferenceStep))

# ============================================================================
# Simple LLM Provider Interface
# ============================================================================

class LLMProvider(ABC):
    """Simplified LLM provider interface."""
    
    @abstractmethod
    async def initialize(self) -> None:
        pass
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        pass
    
    @abstractmethod
    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass

class MockLLMProvider(LLMProvider):
    """Mock provider for demonstration."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = config.get('model', 'mock-model')
    
    async def initialize(self) -> None:
        print(f"Initialized mock LLM provider with model: {self.model}")
    
    async def generate(self, prompt: str) -> str:
        # Simulate processing time
        await asyncio.sleep(0.1)
        return f"Mock response to: {prompt[:50]}..."
    
    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        words = ["This", "is", "a", "mock", "streaming", "response"]
        for word in words:
            yield word + " "
            await asyncio.sleep(0.05)
    
    async def close(self) -> None:
        print("Mock LLM provider closed")

# ============================================================================
# New Chat Service
# ============================================================================

class ChatService:
    """Simplified chat service using pipelines."""
    
    def __init__(self, pipeline: InferencePipeline, chat_history_service=None):
        self.pipeline = pipeline
        self.chat_history_service = chat_history_service
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def process_chat(self, message: str, collection_name: str = "", 
                          system_prompt_id: Optional[str] = None,
                          session_id: Optional[str] = None,
                          user_id: Optional[str] = None,
                          api_key: Optional[str] = None,
                          config: Dict[str, Any] = None) -> Dict[str, Any]:
        
        # Create processing context
        context = ProcessingContext()
        context.message = message
        context.collection_name = collection_name
        context.system_prompt_id = system_prompt_id
        context.config = config or {}
        
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

# ============================================================================
# Usage Example
# ============================================================================

async def main():
    """Demonstrate the new architecture."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create service container
    container = ServiceContainer()
    
    # Register services (in real implementation, these would be actual services)
    container.register_singleton('config', {'inference_only': False})
    
    # Mock services for demonstration
    class MockGuardrail:
        async def check_safety(self, message: str):
            return True, None  # Always safe for demo
    
    class MockRetriever:
        async def get_relevant_context(self, query: str, collection_name: str):
            return [
                {
                    'content': f'Mock relevant content for: {query}',
                    'metadata': {'source': 'mock_doc.txt', 'title': 'Mock Document'},
                    'confidence': 0.85
                }
            ]
    
    class MockReranker:
        async def rerank(self, query: str, docs: List[Dict[str, Any]]):
            return docs  # Return as-is for demo
    
    # Register mock services
    container.register_singleton('guardrail_service', MockGuardrail())
    container.register_singleton('retriever', MockRetriever())
    container.register_singleton('reranker_service', MockReranker())
    
    # Create and register LLM provider
    llm_provider = MockLLMProvider({'model': 'demo-model'})
    await llm_provider.initialize()
    container.register_singleton('llm_provider', llm_provider)
    
    # Build pipeline
    pipeline = InferencePipelineBuilder.build_standard_pipeline(container)
    
    # Create chat service
    chat_service = ChatService(pipeline)
    
    # Process a chat message
    response = await chat_service.process_chat(
        message="What is the capital of France?",
        collection_name="general_knowledge",
        config={'inference_only': False}
    )
    
    print("Response:", response)
    
    # Cleanup
    await llm_provider.close()

if __name__ == "__main__":
    asyncio.run(main())

# ============================================================================
# Benefits Demonstration
# ============================================================================

"""
Benefits of this architecture:

1. LOOSE COUPLING:
   - LLM providers only handle inference
   - Services don't directly reference each other
   - Easy to swap implementations

2. EASY TESTING:
   # Test individual steps
   context = ProcessingContext()
   context.message = "test"
   step = SafetyFilterStep(mock_container)
   result = await step.process(context)

3. FLEXIBLE EXTENSION:
   # Add custom step
   class CustomStep(PipelineStep):
       def should_execute(self, context):
           return True
       
       async def process(self, context):
           # Custom logic
           return context
   
   pipeline.add_step(CustomStep)

4. CONFIGURATION-DRIVEN:
   - Steps decide if they should execute
   - No hard dependencies in constructors
   - Easy to enable/disable features

5. BETTER ERROR HANDLING:
   - Errors stop pipeline gracefully
   - Clear error propagation
   - Individual step error handling

6. SINGLE RESPONSIBILITY:
   - Each step has one job
   - LLM providers only do inference
   - Clear separation of concerns
""" 