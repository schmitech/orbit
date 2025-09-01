# Vector Stores Integration Guide

## Overview

The vector stores system is integrated into the ORBIT server to provide template embedding capabilities for adapters that need vector similarity search, such as the intent SQL adapter.

## Integration Points

### 1. Service Factory (`server/services/service_factory.py`)

**Changes Made:**
- Added `_initialize_vector_store_manager()` method
- Called during full mode initialization (not inference-only mode)
- Creates a singleton `StoreManager` instance and stores it in `app.state.vector_store_manager`

**Key Features:**
- **Conditional Loading**: Only initializes if vector stores are enabled in config
- **Lazy Initialization**: Store manager is created but actual stores are only initialized when needed
- **Graceful Degradation**: Continues startup even if vector stores fail to initialize

**Configuration Detection:**
```python
# Checks for enabled vector stores in config
vector_stores_config = config.get('vector_stores', {})
for store_type in ['chroma', 'pinecone', 'qdrant']:
    if vector_stores_config.get(store_type, {}).get('enabled', False):
        vector_stores_enabled = True
```

### 2. Dynamic Adapter Manager (`server/services/dynamic_adapter_manager.py`)

**Changes Made:**
- Enhanced `_load_adapter()` method to inject vector store manager into adapters
- Added embedding initialization for adapters that support it

**Key Features:**
- **Automatic Detection**: Detects adapters with `initialize_embeddings` method
- **Dependency Injection**: Passes `vector_store_manager` from app state to adapters
- **Fallback Support**: Falls back to standalone initialization if manager not available

**Integration Logic:**
```python
# After adapter initialization
if hasattr(retriever, 'domain_adapter') and retriever.domain_adapter:
    domain_adapter = retriever.domain_adapter
    if hasattr(domain_adapter, 'initialize_embeddings'):
        vector_store_manager = getattr(self.app_state, 'vector_store_manager', None)
        if vector_store_manager:
            await domain_adapter.initialize_embeddings(vector_store_manager)
```

### 3. Intent Adapter (`server/retrievers/adapters/intent/intent_adapter.py`)

**Changes Made:**
- Added optional import of vector stores to prevent import errors
- Enhanced `initialize_embeddings()` method to accept vector store manager
- Added graceful fallback when vector stores aren't available

**Key Features:**
- **Optional Dependency**: Works with or without vector stores module
- **Manager Integration**: Uses global vector store manager when available
- **Backward Compatibility**: Falls back to standalone initialization

## Usage Flow

### 1. Server Startup
```
1. ServiceFactory initializes vector store manager (if enabled)
2. Vector store manager is stored in app.state.vector_store_manager
3. Dynamic adapter manager is initialized with app state reference
```

### 2. Adapter Loading
```
1. Adapter is requested (e.g., via API)
2. Dynamic adapter manager loads and initializes adapter
3. If adapter has domain_adapter with initialize_embeddings:
   - Vector store manager is passed from app.state
   - Embeddings are initialized with shared store manager
```

### 3. Template Embedding Usage
```
1. Intent adapter searches for similar SQL templates
2. Uses TemplateEmbeddingStore with shared vector store
3. Vector searches return ranked template matches
```

## Configuration

### Required Configuration (`config/stores.yaml`)

```yaml
# Store manager configuration
store_manager:
  enabled: true
  cleanup_interval: 300
  ephemeral_max_age: 3600
  auto_cleanup: true

# Vector stores configuration
vector_stores:
  chroma:
    enabled: true
    default_config:
      store_type: "vector"
      connection_params:
        persist_directory: "./chroma_db"
        distance_function: "cosine"
        allow_reset: false
      pool_size: 5
      timeout: 30
      cache_ttl: 1800
      ephemeral: false
      auto_cleanup: true
```

### Adapter Configuration (`config/config.yaml`)

```yaml
adapters:
  - name: intent_postgres
    enabled: true
    datasource: postgres
    adapter: intent
    implementation: retrievers.implementations.intent.intent_postgresql_retriever.IntentPostgreSQLRetriever
    config:
      # Intent adapter specific config
      use_embeddings: true
      embedding_store_config:
        store_type: chroma
        collection_name: sql_templates_postgres
```

## Benefits

### 1. **Separation of Concerns**
- Vector storage is decoupled from adapter logic
- Adapters focus on domain-specific functionality
- Store management is centralized

### 2. **Resource Efficiency**
- Shared vector store connections across adapters
- Lazy initialization reduces startup time
- Connection pooling and caching

### 3. **Flexibility**
- Easy to add new vector store implementations
- Adapters can work with or without embeddings
- Configuration-driven enabling/disabling

### 4. **Scalability**
- Single store manager handles multiple adapters
- Efficient resource usage
- Easy horizontal scaling

## Extension Points

### Adding New Vector Store Types
1. Create implementation in `vector_stores/implementations/`
2. Register in `StoreManager._register_store_classes()`
3. Add configuration support in `config/stores.yaml`

### Creating Embedding-Enabled Adapters
1. Add `use_embeddings` parameter to adapter
2. Initialize `TemplateEmbeddingStore` or similar service
3. Implement `initialize_embeddings(vector_store_manager=None)` method
4. Use vector search in adapter logic

### Custom Embedding Services
1. Create service class in `vector_stores/services/`
2. Use `BaseVectorStore` instances from store manager
3. Implement domain-specific embedding logic

## Error Handling

The integration includes comprehensive error handling:

- **Import Errors**: Gracefully handles missing vector stores module
- **Configuration Errors**: Continues startup with warnings
- **Store Failures**: Falls back to non-embedding mode
- **Connection Issues**: Retries and circuit breaker patterns

## Testing

To test the integration:

1. **With Vector Stores Enabled**:
   - Set `vector_stores.chroma.enabled: true` in config
   - Create intent adapter
   - Verify embedding initialization in logs

2. **Without Vector Stores**:
   - Disable vector stores in config
   - Verify adapters work without embeddings
   - Check graceful degradation

3. **Module Not Available**:
   - Remove vector_stores module
   - Verify server starts without errors
   - Check adapter falls back to basic mode