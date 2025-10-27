# Reranker Architecture

## Overview

The reranker service enhances retrieval accuracy by reordering retrieved documents based on their relevance to the user's query. This document explains the new unified reranker architecture implemented in ORBIT v1.6.0+.

## Architecture

The reranker system is built on three key components:

### 1. Unified AI Services Architecture

Rerankers use the same `AIServiceFactory` pattern as embeddings and inference services:

```python
from ai_services.factory import AIServiceFactory
from ai_services.base import ServiceType

# Create a reranking service
service = AIServiceFactory.create_service(
    ServiceType.RERANKING,
    provider='ollama',
    config=config
)
```

### 2. Singleton Service Manager

The `RerankingServiceManager` implements singleton pattern for efficient service reuse:

```python
from services.reranker_service_manager import RerankingServiceManager

# Get or create a cached reranker service
reranker = RerankingServiceManager.create_reranker_service(
    config=config,
    provider_name='ollama'
)
```

**Key Features:**
- Thread-safe caching by `provider:base_url:model`
- Shared instances across adapters
- Automatic service lifecycle management

### 3. Pipeline Integration

The `DocumentRerankingStep` integrates seamlessly into the inference pipeline:

```
SafetyFilter → LanguageDetection → ContextRetrieval
    → DocumentReranking → LLMInference → ResponseValidation
```

## Configuration

### Global Configuration

Configure rerankers in `config/rerankers.yaml`:

```yaml
# Global reranker configuration
reranker:
  provider: "ollama"  # Default provider
  enabled: true       # Enable reranking globally

# Provider-specific configurations
rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"
    temperature: 0.0
    batch_size: 5
    top_n: null  # Optional default top_n

    # Retry configuration for cold starts
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

### Adapter-Level Configuration

Override reranker settings per adapter in `config/adapters.yaml`:

```yaml
adapters:
  - name: "qa-sql"
    enabled: true
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"

    # Override default providers
    inference_provider: "ollama"
    embedding_provider: "ollama"
    reranker_provider: "ollama"  # Optional: adapter-specific reranker

    config:
      max_results: 10
      reranker_top_n: 5  # Optional: limit reranked results
```

## How It Works

### 1. Document Retrieval

First, the adapter retrieves relevant documents:

```python
# ContextRetrievalStep retrieves documents
docs = await retriever.get_relevant_context(
    query="What is ORBIT?",
    adapter_name="qa-sql"
)
# Returns: [doc1, doc2, doc3, ..., doc10]
```

### 2. Document Reranking

The reranker scores and reorders documents by relevance:

```python
# DocumentRerankingStep reranks documents
reranked = await reranker.rerank(
    query="What is ORBIT?",
    documents=[doc.content for doc in docs],
    top_n=5
)
# Returns: [
#   {'index': 7, 'score': 0.95, 'text': 'ORBIT is...'},
#   {'index': 2, 'score': 0.87, 'text': 'ORBIT provides...'},
#   {'index': 0, 'score': 0.82, 'text': 'The ORBIT system...'},
#   ...
# ]
```

### 3. Context Formation

The LLM receives the best-ranked documents:

```python
# Documents reordered by relevance
context = format_context(reranked_docs)
# LLM gets the most relevant information first
```

### 4. Technical Details: How Rerankers Process Documents

Different reranker implementations use different approaches to score document relevance:

#### Dedicated Reranking Models (Cohere, Jina, Voyage)

These providers use specialized neural models trained specifically for reranking:

**API Request:**
```json
POST https://api.cohere.ai/v1/rerank
{
  "query": "How much does Spring Soccer Club cost?",
  "documents": [
    "Spring Soccer Club costs $39.6.",
    "Spring Soccer Series costs $38.06.",
    "Spring Soccer Tournament costs $54.29."
  ],
  "model": "rerank-english-v3.0",
  "top_n": 3
}
```

**API Response:**
```json
{
  "results": [
    {
      "index": 0,
      "relevance_score": 0.9999975,
      "document": {"text": "Spring Soccer Club costs $39.6."}
    },
    {
      "index": 1,
      "relevance_score": 0.9990188,
      "document": {"text": "Spring Soccer Series costs $38.06."}
    },
    {
      "index": 2,
      "relevance_score": 0.014009566,
      "document": {"text": "Spring Soccer Tournament costs $54.29."}
    }
  ]
}
```

**Key Points:**
- Dedicated reranking models understand **semantic similarity**, not just keyword overlap
- Can distinguish "Club" vs "Series" vs "Tournament" semantically
- Scores reflect true relevance: 99.99% for exact match, 1.4% for unrelated document
- Fast inference (100-500ms for small batches)

#### LLM-Based Reranking (OpenAI, Anthropic)

These providers use general-purpose language models with prompt engineering:

**Reranking Prompt:**
```
You are a relevance scoring system. Rate each document's relevance to the query on a scale of 0.0 to 1.0:

Query: How much does Spring Soccer Club cost?

Document 0: Question: How much does Spring Soccer Club cost?
            Answer: Spring Soccer Club costs $39.6.

Document 1: Question: How much does Spring Soccer Series cost?
            Answer: Spring Soccer Series costs $38.06.

Document 2: Question: How much does Spring Soccer Tournament cost?
            Answer: The Spring Soccer Tournament costs $54.29.

Rate each document's relevance (0.0 = not relevant, 1.0 = highly relevant).
Provide scores as JSON: {"scores": [0.99, 0.85, 0.15]}

Only output the JSON, no other text.
```

**LLM Response:**
```json
{
  "scores": [0.99, 0.85, 0.15]
}
```

**Key Points:**
- Uses powerful language understanding but slower (200-1000ms)
- Good for complex queries requiring nuanced judgment
- Higher API costs per reranking operation
- Can explain reasoning if needed (with modified prompt)

#### Local Reranking (Ollama)

Uses locally-hosted reranking models via Ollama:

**Request to Ollama:**
```python
# Ollama uses the embedding endpoint for reranking models
POST http://localhost:11434/api/generate
{
  "model": "xitao/bge-reranker-v2-m3",
  "prompt": f"Query: {query}\n\nDocument: {document}",
  "stream": false
}
```

**Processing:**
- Computes relevance score for each query-document pair
- Uses cross-encoder architecture (processes query+document together)
- Returns normalized scores between 0.0 and 1.0

**Key Points:**
- Free and private (no data sent to external APIs)
- Requires local GPU/CPU resources
- Latency: 50-200ms per batch on modern hardware
- Quality comparable to API-based rerankers

#### Why Reranking Improves Results

**Example: Token-Based Retrieval vs Semantic Reranking**

Initial token-based retrieval finds all documents with matching keywords:
```
Query: "How much does Spring Soccer Club cost?"
Tokens: ['much', 'spring', 'soccer', 'club', 'cost']

Retrieved Documents (all have "spring" + "soccer"):
1. Spring Soccer Club ($39.6)         - tokens: 5/5 match
2. Spring Soccer Series ($38.06)      - tokens: 4/5 match
3. Spring Soccer Tournament ($54.29)  - tokens: 4/5 match
```

All three look similar to keyword search! But semantic reranking understands meaning:

```
Reranked Results:
1. Spring Soccer Club - 0.9999975 (99.99%) ✅ EXACT semantic match
2. Spring Soccer Series - 0.9990188 (99.90%) - Similar but different
3. Spring Soccer Tournament - 0.014 (1.4%) ❌ NOT what user asked for
```

The reranker **semantically understands** that:
- "Club" in query matches "Club" in document (not "Tournament")
- "How much does X cost?" matches "X costs $Y" structure
- Documents 2 and 3 are about different programs

This prevents the LLM from receiving irrelevant context and hallucinating answers.

## Service Resolution

The reranker service is resolved in this order:

1. **Adapter-level override**: If `reranker_provider` is specified in adapter config
2. **Global default**: Use the provider specified in `reranker.provider`
3. **Graceful degradation**: If reranker fails, use original document order

## Implementation Details

### Singleton Caching

Services are cached by unique key:

```python
# Cache key format: "provider:base_url:model"
cache_key = "ollama:http://localhost:11434:bge-reranker-v2-m3"

# Same key = same instance (singleton)
service1 = RerankingServiceManager.create_reranker_service(config, 'ollama')
service2 = RerankingServiceManager.create_reranker_service(config, 'ollama')
assert service1 is service2  # True - same instance
```

### Thread Safety

All caching uses thread-safe locks:

```python
with self._reranker_cache_lock:
    if cache_key in self._reranker_cache:
        return self._reranker_cache[cache_key]
    # ... create new instance
```

### Metadata Preservation

Original document metadata is preserved after reranking:

```python
original_doc = {
    'content': 'ORBIT is a RAG framework',
    'metadata': {'source': 'docs/README.md', 'page': 1},
    'confidence': 0.75
}

reranked_doc = {
    'content': 'ORBIT is a RAG framework',
    'metadata': {'source': 'docs/README.md', 'page': 1},  # Preserved
    'confidence': 0.75,  # Preserved
    'relevance': 0.95,   # New score from reranker
    'reranked': True     # Marked as reranked
}
```

## Available Rerankers

### Ollama Reranker (Local, Free)

Uses local reranking models via Ollama:

```yaml
rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "xitao/bge-reranker-v2-m3:latest"
    temperature: 0.0
    batch_size: 5
```

**Recommended Models:**
- `xitao/bge-reranker-v2-m3:latest` - Multilingual, high quality
- `jinaai/jina-reranker-v1-base-en` - English, fast
- `BAAI/bge-reranker-large` - High accuracy

**Pros:** Free, private, no API costs
**Cons:** Requires local Ollama setup, slower than API-based

---

### Cohere Rerank API (Excellent Quality)

Industry-leading reranking quality with multilingual support:

```yaml
rerankers:
  cohere:
    api_key: ${COHERE_API_KEY}
    model: "rerank-english-v3.0"  # or "rerank-multilingual-v3.0"
    batch_size: 5
    max_chunks_per_doc: 10
```

**Pros:** Excellent quality, multilingual (100+ languages), fast API
**Cons:** Requires API key, usage costs
**Best for:** Production deployments, multilingual content

---

### Jina AI Reranker (Fast, Good Quality)

Purpose-built reranking models via API:

```yaml
rerankers:
  jina:
    api_key: ${JINA_API_KEY}
    model: "jina-reranker-v2-base-multilingual"
    batch_size: 5
```

**Pros:** Good quality, fast, multilingual, good cost/quality ratio
**Cons:** Requires API key
**Best for:** High-volume applications, cost-conscious deployments

---

### OpenAI Reranker (GPT-Powered)

Uses GPT models via prompt engineering for relevance scoring:

```yaml
rerankers:
  openai:
    api_key: ${OPENAI_API_KEY}
    model: "gpt-4o-mini"
    temperature: 0.0
    batch_size: 3
```

**Pros:** Powerful language understanding, good for complex queries
**Cons:** Higher latency, higher cost, not dedicated reranker
**Best for:** Complex queries requiring deep understanding

---

### Anthropic Reranker (Claude-Powered)

Uses Claude models for nuanced relevance judgments:

```yaml
rerankers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: "claude-3-haiku-20240307"
    temperature: 0.0
    batch_size: 3
```

**Pros:** Excellent instruction following, nuanced judgments
**Cons:** Higher latency, higher cost, not dedicated reranker
**Best for:** Queries requiring subtle relevance distinctions

---

### Voyage AI Reranker (Cost-Effective)

Purpose-built reranking with good performance/cost ratio:

```yaml
rerankers:
  voyage:
    api_key: ${VOYAGE_API_KEY}
    model: "rerank-lite-1"
    truncation: true
```

**Pros:** Good performance, cost-effective, simple API
**Cons:** Requires API key
**Best for:** Budget-conscious deployments with good quality needs

## Pipeline Step Details

### DocumentRerankingStep

**Location**: `server/inference/pipeline/steps/document_reranking.py`

**Execution Conditions:**

The step executes when:
- Documents were retrieved (`context.retrieved_docs` is not empty)
- Reranking is enabled (global or adapter-level)
- Context is not blocked
- Reranker service is available

**Graceful Degradation:**

If reranking fails:
- Original document order is preserved
- Error is logged but pipeline continues
- LLM still receives the retrieved documents

**Example:**

```python
from inference.pipeline.steps import DocumentRerankingStep
from inference.pipeline.service_container import ServiceContainer

# Create container with reranker service
container = ServiceContainer()
container.register('config', config)
container.register('reranker_service', reranker_service)

# Create step
step = DocumentRerankingStep(container)

# Process context
context = ProcessingContext(
    message="What is ORBIT?",
    adapter_name="qa-sql",
    parameters={}
)
context.retrieved_docs = [...]  # Documents from retrieval

# Rerank documents
reranked_context = await step.process(context)
# context.retrieved_docs now contains reranked documents
```

## Performance Considerations

### When to Use Reranking

**Use reranking when:**
- Retrieval returns many documents (>5)
- Initial retrieval uses fast but less accurate methods (BM25, simple embeddings)
- Query is complex or ambiguous
- Accuracy is more important than latency

**Skip reranking when:**
- Only 1-3 documents retrieved
- Retrieval already highly accurate
- Real-time response required (every millisecond counts)
- Simple factual queries

### Latency Impact

Typical reranking latency:
- **Local (Ollama)**: 50-200ms for 10 documents
- **API-based**: 100-500ms depending on provider

### Optimization Tips

1. **Limit documents**: Use `max_results` in retrieval config
2. **Set top_n**: Rerank only top N documents
3. **Batch processing**: Configure `batch_size` for large document sets
4. **Cache results**: Enable caching for repeated queries

## Monitoring

### Reranking Metadata

The pipeline adds reranking metadata to the context:

```python
context.metadata['reranking'] = {
    'provider': 'ollama',
    'model': 'bge-reranker-v2-m3',
    'original_count': 10,
    'reranked_count': 5,
    'top_scores': [0.95, 0.87, 0.82]
}
```

### Logging

Reranking operations are logged:

```
INFO - Reranking 10 documents for query: "What is ORBIT?"
DEBUG - Successfully reranked documents: 10 -> 5
DEBUG - Top scores: [0.95, 0.87, 0.82, 0.78, 0.71]
```

## Troubleshooting

### Reranker Not Running

**Symptoms:**
- Documents not reordered
- No reranking metadata in response

**Checks:**
1. Verify reranking is enabled: `reranker.enabled: true`
2. Check adapter specifies `reranker_provider` (if using adapter-level)
3. Ensure documents were retrieved
4. Check logs for reranker service initialization

### Poor Reranking Quality

**Solutions:**
1. Try different reranking models
2. Adjust `temperature` (lower = more deterministic)
3. Increase `top_n` to get more results
4. Verify query and documents are in same language

### Slow Reranking

**Solutions:**
1. Reduce number of documents to rerank
2. Use faster reranking model
3. Enable batch processing with appropriate `batch_size`
4. Consider using API-based reranker with better infrastructure

### Reranker Service Fails

**Fallback Behavior:**
- Original document order is preserved
- Error is logged
- Pipeline continues normally
- LLM still generates response

## Migration Guide

### From Old Reranker (v1.5.x and earlier)

The old reranker implementation used:
```python
from rerankers import RerankerFactory
reranker = RerankerFactory.create(config)
```

The new implementation uses:
```python
from services.reranker_service_manager import RerankingServiceManager
reranker = RerankingServiceManager.create_reranker_service(config, provider)
```

**Configuration Changes:**

Old `config/rerankers.yaml`:
```yaml
rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "bge-reranker"
```

New `config/rerankers.yaml`:
```yaml
reranker:
  provider: "ollama"
  enabled: true

rerankers:
  ollama:
    base_url: "http://localhost:11434"
    model: "bge-reranker"
    retry: {...}
    timeout: {...}
```

**Benefits:**
- ✅ Singleton pattern for better performance
- ✅ Unified architecture with other AI services
- ✅ Better error handling and retry logic
- ✅ Thread-safe caching
- ✅ Adapter-level overrides

## API Reference

### RerankingServiceManager

```python
class RerankingServiceManager:
    @classmethod
    def create_reranker_service(
        cls,
        config: Dict[str, Any],
        provider_name: Optional[str] = None
    ) -> RerankingService:
        """Create or return cached reranker service."""

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached instances."""
```

### DocumentRerankingStep

```python
class DocumentRerankingStep(PipelineStep):
    def should_execute(self, context: ProcessingContext) -> bool:
        """Check if reranking should run."""

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Rerank documents in context."""
```

### RerankingService Interface

```python
class RerankingService:
    async def initialize(self) -> bool:
        """Initialize the reranking service."""

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Rerank documents by relevance to query."""

    async def close(self) -> None:
        """Clean up resources."""
```

## Best Practices

1. **Start with defaults**: Use global configuration first
2. **Override when needed**: Use adapter-level config for specific needs
3. **Monitor performance**: Track reranking latency and quality
4. **Test different models**: Experiment to find best model for your use case
5. **Set reasonable top_n**: Don't rerank more documents than needed
6. **Use retry/timeout**: Configure for production reliability

## Related Documentation

- [Pipeline Inference Architecture](pipeline-inference-architecture.md)
- [Adapter Configuration](adapter-configuration.md)
- [Vector Retriever Architecture](vector-retriever-architecture.md)
- [SQL Retriever Architecture](sql-retriever-architecture.md)
