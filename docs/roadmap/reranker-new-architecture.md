# Reranker Configuration Implementation Plan

## Overview

Implement a complete reranker configuration system using the new unified AI services architecture, enabling adapters to optionally specify reranker providers for improving document retrieval relevance.

## Phase 1: Configuration File Structure

### Update `config/rerankers.yaml`

Restructure to match `embeddings.yaml` and `inference.yaml` patterns:

```yaml
# Global reranker configuration
reranker:
  provider: "ollama"  # Default reranker provider
  enabled: true       # Whether reranking is enabled globally

# Provider-specific configurations
rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"
    temperature: 0.0
    batch_size: 5
    top_n: null  # Optional default top_n
    # Retry configuration for handling cold starts
    retry:
      enabled: true
      max_retries: 5
      initial_wait_ms: 2000
      max_wait_ms: 30000
      exponential_base: 2
    # Timeout configuration
    timeout:
      connect: 10000
      total: 60000
      warmup: 45000
```

## Phase 2: Service Integration

### Create Reranker Service Singleton Factory

Create `server/services/reranker_service_manager.py`:

- Implement singleton pattern like `EmbeddingServiceFactory`
- Use `AIServiceFactory.create_service(ServiceType.RERANKING, provider, config)`
- Cache instances by provider + base_url + model combination
- Support adapter-level provider overrides

Key methods:

- `create_reranker_service(config, provider_name=None)` - returns cached singleton
- `_create_cache_key(provider, config)` - creates unique key for caching
- Thread-safe with locks

### Update Service Factory

Modify `server/services/service_factory.py`:

- Update `_initialize_reranker_service()` to use new unified architecture
- Replace `RerankerFactory.create()` with `RerankingServiceManager.create_reranker_service()`
- Register as singleton in service container during pipeline creation

### Update Pipeline Factory

Modify `server/inference/pipeline_factory.py`:

- In `create_service_container()`, ensure reranker_service is registered as singleton
- Keep existing parameter passing pattern

## Phase 3: Adapter Configuration Support

### Enable Adapter-Level Reranker Override

Update adapter configuration schema in `config/adapters.yaml` examples:

```yaml
adapters:
  - name: "qa-sql"
    enabled: true
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"
    inference_provider: "ollama"  # Existing
    embedding_provider: "ollama"   # Existing
    reranker_provider: "ollama"    # NEW - Optional reranker override
    config:
      # ... existing config
```

### Update Dynamic Adapter Manager

Modify `server/services/dynamic_adapter_manager.py`:

- Add `_reranker_cache` and `_reranker_cache_lock` (similar to embedding/provider caches)
- Add `_get_or_create_reranker()` method for per-adapter reranker initialization
- Pass reranker service to adapter during initialization if specified

## Phase 4: Pipeline Reranking Step

### Create Reranking Pipeline Step

Create `server/inference/pipeline/steps/document_reranking.py`:

```python
class DocumentRerankingStep(PipelineStep):
    """
    Rerank retrieved documents using a reranking service.
    
    This step runs after context retrieval and before LLM inference,
    improving relevance of retrieved documents.
    """
    
    def should_execute(self, context: ProcessingContext) -> bool:
        # Only execute if:
        # 1. Retrieval happened (context.retrieved_docs exists)
        # 2. Reranker service is available in container
        # 3. Adapter config specifies reranker_provider OR global reranker is enabled
        # 4. Not blocked
        pass
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        # Get reranker service from container
        # Extract document texts from context.retrieved_docs
        # Call reranker.rerank(query, documents, top_n)
        # Update context.retrieved_docs with reranked results
        # Update context.formatted_context with reranked documents
        pass
```

Key features:

- Extract text from retrieved docs (handle various document formats)
- Preserve document metadata after reranking
- Use `top_n` from adapter config or reranker config
- Log reranking metrics (time, score changes)
- Handle errors gracefully (skip reranking on failure, don't break pipeline)

### Update Pipeline Steps Init

Modify `server/inference/pipeline/steps/__init__.py`:

- Import `DocumentRerankingStep`
- Add to `__all__` list

### Update Pipeline Builder

Modify `server/inference/pipeline/pipeline.py`:

- In `InferencePipelineBuilder.build_standard_pipeline()`:
        - Add `DocumentRerankingStep(container)` after `ContextRetrievalStep` and before `LLMInferenceStep`
- Step order: SafetyFilter → LanguageDetection → ContextRetrieval → **DocumentReranking** → LLMInference → ResponseValidation

## Phase 5: Context Propagation

### Update ProcessingContext

Modify `server/inference/pipeline/base.py` if needed:

- Ensure `retrieved_docs` supports reranked document format
- Add optional `reranking_metadata` field to track reranking info (scores, provider used)

## Phase 6: Testing & Validation

### Verify Integration Points

1. Config loads correctly from `rerankers.yaml`
2. Service singleton creation works
3. Adapter-level override works in `config/adapters.yaml`
4. Pipeline step executes conditionally
5. Documents are properly reranked
6. Formatted context reflects reranked order

### Test Cases to Validate

- Reranking with global provider (no adapter override)
- Reranking with adapter-level provider override
- Skip reranking when adapter doesn't specify reranker_provider
- Skip reranking when no documents retrieved
- Handle reranker service initialization failures gracefully

## Implementation Order

1. Update `config/rerankers.yaml` structure
2. Create `server/services/reranker_service_manager.py`
3. Update `server/services/service_factory.py` 
4. Create `server/inference/pipeline/steps/document_reranking.py`
5. Update `server/inference/pipeline/steps/__init__.py`
6. Update `server/inference/pipeline/pipeline.py`
7. Update `server/services/dynamic_adapter_manager.py` for adapter-level support
8. Test with example adapter configuration

## Files to Modify

- `config/rerankers.yaml` - restructure configuration
- `server/services/reranker_service_manager.py` - NEW FILE
- `server/services/service_factory.py` - update reranker initialization
- `server/inference/pipeline_factory.py` - ensure proper service registration
- `server/inference/pipeline/steps/document_reranking.py` - NEW FILE
- `server/inference/pipeline/steps/__init__.py` - add new step
- `server/inference/pipeline/pipeline.py` - add step to pipeline builder
- `server/inference/pipeline/base.py` - potentially add reranking_metadata
- `server/services/dynamic_adapter_manager.py` - add reranker caching
- `config/adapters.yaml` - update examples with reranker_provider

## Key Design Principles

- Follow embeddings.yaml pattern exactly for consistency
- Use unified AI services architecture (`ServiceType.RERANKING`)
- Implement singleton pattern for service reuse
- Make reranking optional and non-breaking
- Support both global and adapter-level configuration
- Graceful degradation if reranker fails