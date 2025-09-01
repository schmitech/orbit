# Vector Stores Architecture

## Directory Structure

```
vector_stores/
├── base/                      # Core abstractions and management
│   ├── base_store.py         # Abstract base class for all stores
│   ├── base_vector_store.py  # Base class for vector-specific operations
│   └── store_manager.py      # Lifecycle management and registry
│
├── implementations/           # Concrete vector store implementations
│   └── chroma_store.py       # ChromaDB implementation
│   └── (future: pinecone_store.py, qdrant_store.py, etc.)
│
├── services/                  # High-level services using vector stores
│   └── template_embedding_store.py  # SQL template embedding management
│
└── store_factory.py          # Factory functions for store creation
```

## Inheritance Tree

```
BaseStore (ABC)
    │
    ├── BaseVectorStore (ABC)
    │       │
    │       └── ChromaStore (concrete)
    │       └── (future: PineconeStore, QdrantStore, etc.)
    │
    └── (future: BaseRelationalStore, BaseDocumentStore, etc.)

TemplateEmbeddingStore (service layer - uses BaseVectorStore instances)
    └── Composition: uses StoreManager to manage vector stores
```

## Class Responsibilities

### Base Layer (`base/`)

1. **BaseStore**
   - Abstract base for all storage types
   - Provides: connection management, health checks, retry logic
   - Common interface: connect(), disconnect(), health_check(), get_stats()

2. **BaseVectorStore** 
   - Extends BaseStore for vector-specific operations
   - Abstract methods: add_vectors(), search_vectors(), manage collections
   - Utility methods: similarity calculations, batch operations

3. **StoreManager**
   - Singleton pattern for managing store instances
   - Handles store lifecycle (creation, removal, cleanup)
   - Registry for store implementations
   - Configuration management

### Implementation Layer (`implementations/`)

1. **ChromaStore**
   - Concrete implementation using ChromaDB
   - Implements all BaseVectorStore abstract methods
   - Handles ChromaDB-specific configuration
   - Supports persistent and ephemeral storage

### Service Layer (`services/`)

1. **TemplateEmbeddingStore**
   - High-level service for SQL template embeddings
   - Uses StoreManager to get/create vector stores
   - Provides template-specific operations
   - Handles caching and batch operations

### Factory Layer

1. **store_factory.py**
   - Factory functions for creating configured stores
   - Integration with configuration system
   - Convenience methods for common use cases

## Design Principles

1. **Separation of Concerns**
   - Base: Abstract interfaces and common functionality
   - Implementations: Vendor-specific code
   - Services: Business logic and domain-specific operations
   - Factory: Object creation and configuration

2. **Dependency Inversion**
   - High-level modules (services) depend on abstractions (base classes)
   - Low-level modules (implementations) implement abstractions
   - Easy to swap implementations without changing service code

3. **Single Responsibility**
   - Each class has one clear purpose
   - StoreManager handles lifecycle, not business logic
   - Implementations focus on vendor-specific details
   - Services provide domain-specific functionality

4. **Open/Closed Principle**
   - Open for extension (add new store implementations)
   - Closed for modification (base interfaces remain stable)

## Usage Examples

### Basic Vector Store Usage
```python
from vector_stores import ChromaStore, StoreConfig

config = StoreConfig(
    name="my_vectors",
    connection_params={"persist_directory": "./chroma_db"},
    ephemeral=False
)

store = ChromaStore(config)
await store.connect()
await store.add_vectors(vectors, ids, metadata)
results = await store.search_vectors(query_vector, limit=10)
```

### Using Store Manager
```python
from vector_stores import get_store_manager

manager = get_store_manager("config/stores.yaml")
store = await manager.get_or_create_store(
    name="templates",
    store_type="chroma"
)
```

### Template Embedding Service
```python
from vector_stores import TemplateEmbeddingStore

template_store = TemplateEmbeddingStore(
    store_name="sql_templates",
    store_type="chroma",
    collection_name="templates"
)
await template_store.initialize()
await template_store.add_template(template_id, template_data, embedding)
similar = await template_store.search_similar_templates(query_embedding)
```

## Extension Points

1. **Adding New Vector Stores**
   - Create new class in `implementations/`
   - Extend `BaseVectorStore`
   - Implement all abstract methods
   - Register in `StoreManager._register_store_classes()`

2. **Adding New Store Types**
   - Create new base class (e.g., `BaseRelationalStore`)
   - Extend `BaseStore`
   - Define type-specific abstract methods
   - Create implementations in appropriate subdirectory

3. **Adding New Services**
   - Create new service in `services/`
   - Use `StoreManager` to get store instances
   - Focus on domain-specific logic
   - Compose functionality from base stores

## Benefits of This Architecture

1. **Modularity**: Each component can be developed, tested, and maintained independently
2. **Testability**: Easy to mock base classes for unit testing
3. **Flexibility**: New implementations can be added without modifying existing code
4. **Reusability**: Base classes provide common functionality for all implementations
5. **Clarity**: Clear separation between abstraction, implementation, and service layers
6. **Maintainability**: Changes to vendor-specific code don't affect service layer
7. **Scalability**: Easy to add new storage backends as needed