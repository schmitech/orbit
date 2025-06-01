# Vector Retriever Architecture Summary

The `AbstractVectorRetriever` architecture is designed to be **database-agnostic** and supports any vector database. The base class provides common functionality while allowing database-specific optimizations and domain specializations.

## Architecture Hierarchy

```
BaseRetriever (abstract base for all retrievers)
└── AbstractVectorRetriever (database-agnostic vector functionality)
    ├── vector/
    │   ├── ChromaRetriever (ChromaDB-specific implementation)
    │   ├── MilvusRetriever (Milvus-specific implementation)
    │   ├── PineconeRetriever (Pinecone-specific implementation)
    │   ├── ElasticsearchRetriever (Elasticsearch-specific implementation)
    │   └── RedisRetriever (Redis-specific implementation)
    └── qa/
        └── QAChromaRetriever (QA domain specialization of ChromaDB)
```

## Supported Vector Databases

### ✅ Currently Implemented

| Database | Implementation | Status | Special Features | Domain Specializations |
|----------|----------------|---------|------------------|------------------------|
| **ChromaDB** | `vector.ChromaRetriever` | ✅ Complete | Local & remote, L2 distance | `qa.QAChromaRetriever` (Q&A) |
| **Milvus** | `vector.MilvusRetriever` | ✅ Complete | Multiple metrics (IP, L2, COSINE) | *Easy to add* |
| **Pinecone** | `vector.PineconeRetriever` | ✅ Complete | Managed cloud, similarity scores | *Easy to add* |
| **Elasticsearch** | `vector.ElasticsearchRetriever` | ✅ Complete | KNN search, text + vector | *Easy to add* |
| **Redis** | `vector.RedisRetriever` | ✅ Complete | RedisSearch, multiple metrics | *Easy to add* |

### 🔄 To Add

| Database | Implementation | Notes |
|----------|----------------|-------|
| **Qdrant** | `vector.QdrantRetriever` | REST API, multiple metrics |
| **Weaviate** | `vector.WeaviateRetriever` | GraphQL API, semantic search |
| **MongoDB** | `vector.MongoDBRetriever` | Atlas Vector Search |

## 🔄 Details

```
BaseRetriever (core functionality for all retrievers)
│
└── AbstractVectorRetriever (database-agnostic vector base)
    │   • Common vector functionality
    │   • Embedding management & integration
    │   • Domain adapter integration
    │   • Abstract methods for DB-specific implementation
    │
    ├── vector/
    │   ├── ChromaRetriever (ChromaDB-specific implementation)
    │   │   • ChromaDB connection management
    │   │   • ChromaDB query execution
    │   │   • L2 distance optimization
    │   │
    │   ├── MilvusRetriever (Milvus-specific)
    │   │   • Multiple distance metrics (IP, L2, COSINE)
    │   │   • Milvus connection via pymilvus
    │   │   • Collection management
    │   │
    │   ├── PineconeRetriever (Pinecone-specific)
    │   │   • Managed cloud service
    │   │   • Direct similarity scores
    │   │   • Namespace support
    │   │
    │   ├── ElasticsearchRetriever (Elasticsearch-specific)
    │   │   • KNN search capabilities
    │   │   • Hybrid text + vector search
    │   │   • Enterprise features
    │   │
    │   └── RedisRetriever (Redis-specific)
    │       • RedisSearch integration
    │       • Multiple distance metrics
    │       • High-performance in-memory
    │
    └── qa/
        └── QAChromaRetriever (QA domain specialization)
            • Question/Answer field prioritization
            • QA-optimized similarity scoring
            • QA-specific result formatting
```

### Code Reuse
- `QAChromaRetriever` inherits all ChromaDB functionality from `ChromaRetriever`
- No duplication of connection management, query execution, etc.
- Focuses only on QA-specific enhancements

### Separation of Concerns
- **Database Logic**: Handled by `ChromaRetriever`, `MilvusRetriever`, etc.
- **Domain Logic**: Handled by specializations like `QAChromaRetriever`
- **Common Logic**: Handled by `AbstractVectorRetriever`

### Extensibility
- Easy to add new vector databases: extend `AbstractVectorRetriever`
- Easy to add domain specializations: extend any database implementation
- Future: `QAMilvusRetriever`, `LegalPineconeRetriever`, etc.

## Configuration Examples

### Multi-Database Configuration

```yaml
# config.yaml
datasources:
  # ChromaDB (local)
  chroma:
    use_local: true
    db_path: "./data/chroma_db"
    max_results: 10
    
  # Milvus (self-hosted)
  milvus:
    host: "localhost"
    port: 19530
    dim: 768
    metric_type: "COSINE"
    max_results: 15
    
  # Pinecone (cloud)
  pinecone:
    api_key: "${PINECONE_API_KEY}"
    host: "https://index-name.pinecone.io"
    namespace: "default"
    max_results: 20
    
  # Elasticsearch (enterprise)
  elasticsearch:
    node: "https://es.company.com:9200"
    auth:
      username: "${ES_USERNAME}"
      password: "${ES_PASSWORD}"
    vector_field: "embedding"
    text_field: "content"
    
  # Redis (high-performance)
  redis:
    host: "localhost"
    port: 6379
    password: "${REDIS_PASSWORD}"
    vector_field: "embedding"
    distance_metric: "COSINE"

adapters:
  # ChromaDB with QA specialization
  - name: "qa-chroma"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa_chroma_retriever.QAChromaRetriever"
    config:
      confidence_threshold: 0.3
      distance_scaling_factor: 200.0
      
  # Generic Milvus adapter
  - name: "general-milvus"
    type: "retriever"
    datasource: "milvus"
    adapter: "generic"
    implementation: "retrievers.implementations.milvus_retriever.MilvusRetriever"
    config:
      confidence_threshold: 0.5
```

## Implementation Examples

### ChromaDB with QA Specialization

```python
from retrievers.implementations.qa_chroma_retriever import QAChromaRetriever

# Configuration
config = {
    "datasources": {
        "chroma": {
            "use_local": True,
            "db_path": "./data/qa_knowledge_chroma",
            "max_results": 10
        }
    },
    "adapters": [{
        "type": "retriever",
        "datasource": "chroma",
        "adapter": "qa",
        "config": {
            "confidence_threshold": 0.3,
            "distance_scaling_factor": 200.0
        }
    }]
}

# Initialize QA-specialized ChromaDB retriever
retriever = QAChromaRetriever(config=config)
await retriever.initialize()
await retriever.set_collection("qa_collection")

# Optimized for Q&A scenarios
results = await retriever.get_relevant_context("How do I configure the system?")
```

### Milvus with Multiple Metrics

```python
from retrievers.implementations.milvus_retriever import MilvusRetriever

# Configuration
config = {
    "datasources": {
        "milvus": {
            "host": "localhost",
            "port": 19530,
            "dim": 768,
            "metric_type": "COSINE",  # or "IP", "L2"
            "max_results": 15
        }
    }
}

# Initialize Milvus retriever
retriever = MilvusRetriever(config=config)
await retriever.initialize()
await retriever.set_collection("documents")

# Use with Milvus-optimized features
results = await retriever.get_relevant_context("machine learning algorithms")
```

### Pinecone Cloud Service

```python
from retrievers.implementations.pinecone_retriever import PineconeRetriever

# Configuration
config = {
    "datasources": {
        "pinecone": {
            "api_key": "your-api-key",
            "host": "https://index-name.pinecone.io",
            "namespace": "production",
            "max_results": 20
        }
    }
}

# Initialize Pinecone retriever
retriever = PineconeRetriever(config=config)
await retriever.initialize()
await retriever.set_collection("knowledge_base")

# Leverage Pinecone's managed service
results = await retriever.get_relevant_context("database optimization")
```

### Elasticsearch Hybrid Search

```python
from retrievers.implementations.elasticsearch_retriever import ElasticsearchRetriever

# Configuration
config = {
    "datasources": {
        "elasticsearch": {
            "node": "https://localhost:9200",
            "auth": {
                "username": "elastic",
                "password": "password"
            },
            "vector_field": "embedding",
            "text_field": "content",
            "max_results": 10
        }
    }
}

# Initialize Elasticsearch retriever
retriever = ElasticsearchRetriever(config=config)
await retriever.initialize()
await retriever.set_collection("documents")

# Use KNN search with Elasticsearch
results = await retriever.get_relevant_context("python programming")
```

## Creating New Vector Database Support

### Step 1: Inherit from AbstractVectorRetriever

```python
from retrievers.base.abstract_vector_retriever import AbstractVectorRetriever

class QdrantRetriever(AbstractVectorRetriever):
    def _get_datasource_name(self) -> str:
        return 'qdrant'
```

### Step 2: Implement Required Abstract Methods

```python
async def initialize_client(self) -> None:
    """Qdrant-specific client initialization"""
    from qdrant_client import QdrantClient
    
    self.qdrant_client = QdrantClient(
        host=self.host,
        port=self.port,
        api_key=self.api_key
    )

async def close_client(self) -> None:
    """Qdrant-specific cleanup"""
    if self.qdrant_client:
        self.qdrant_client.close()

async def set_collection(self, collection_name: str) -> None:
    """Set Qdrant collection"""
    # Verify collection exists
    collections = self.qdrant_client.get_collections()
    if collection_name not in [c.name for c in collections.collections]:
        raise HTTPException(status_code=404, detail="Collection not found")
    self.collection_name = collection_name

async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
    """Qdrant-specific vector search"""
    from qdrant_client.models import SearchRequest
    
    search_result = self.qdrant_client.search(
        collection_name=self.collection_name,
        query_vector=query_embedding,
        limit=top_k
    )
    
    # Convert to standard format
    search_results = []
    for point in search_result:
        search_results.append({
            'document': point.payload.get('content', ''),
            'metadata': point.payload,
            'score': point.score  # Qdrant returns similarity scores
        })
    
    return search_results
```

### Step 3: Add Database-Specific Optimizations

```python
def calculate_similarity_from_distance(self, distance: float) -> float:
    """Qdrant returns similarity scores directly"""
    return float(distance)  # No conversion needed
    
async def get_relevant_context(self, query: str, **kwargs) -> List[Dict[str, Any]]:
    """Override if needed for Qdrant-specific features"""
    # Use parent implementation or customize for Qdrant features
    return await super().get_relevant_context(query, **kwargs)
```

### Step 4: Register with Factory

```python
from retrievers.base.base_retriever import RetrieverFactory
RetrieverFactory.register_retriever('qdrant', QdrantRetriever)
```

## Creating Domain Specializations

### Step 1: Extend a Vector Database Implementation

```python
from retrievers.implementations.milvus_retriever import MilvusRetriever

class QAMilvusRetriever(MilvusRetriever):
    """QA specialization of Milvus retriever"""
    
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        # Add QA-specific configuration
        self.qa_confidence_threshold = 0.3
        self.qa_fields = ['question', 'answer', 'title', 'content']
```

### Step 2: Add Domain-Specific Enhancements

```python
async def initialize(self) -> None:
    """Initialize with QA domain adapter"""
    await super().initialize()
    
    # Create QA-specific domain adapter
    from retrievers.adapters.registry import ADAPTER_REGISTRY
    self.domain_adapter = ADAPTER_REGISTRY.create(
        adapter_type='retriever',
        datasource='milvus',
        adapter_name='qa',
        config=self.config
    )

def calculate_similarity_from_distance(self, distance: float) -> float:
    """QA-enhanced similarity calculation"""
    # Custom logic for QA scenarios
    base_similarity = super().calculate_similarity_from_distance(distance)
    # Apply QA-specific boosts/adjustments
    return base_similarity
```

## Distance Metrics and Similarity Conversion

Different vector databases use different distance metrics. The architecture handles this automatically:

| Database | Metric | Conversion | Notes |
|----------|--------|------------|-------|
| **ChromaDB** | L2 Distance | `1.0 / (1.0 + distance/scale)` | Lower distance = higher similarity |
| **Milvus** | IP/L2/COSINE | Metric-specific | Handles all three metrics |
| **Pinecone** | Similarity Score | Direct use | Already 0-1 similarity |
| **Elasticsearch** | Similarity Score | Direct use | KNN returns similarity |
| **Redis** | Distance/Score | Metric-specific | Depends on configuration |

## Performance Considerations

| Database | Best For | Performance Notes | Scaling |
|----------|----------|-------------------|---------|
| **ChromaDB** | Development, prototyping | Fast local, simple deployment | Single machine |
| **Milvus** | Production, large scale | Excellent performance, distributed | Horizontal scaling |
| **Pinecone** | Serverless, managed | No infrastructure management | Auto-scaling |
| **Elasticsearch** | Hybrid search | Text + vector search | Distributed |
| **Redis** | Low latency | In-memory, sub-ms queries | Memory-bound |

## Migration Between Vector Databases

The abstract interface makes it easy to migrate between vector databases:

```python
# Development: ChromaDB
dev_retriever = ChromaRetriever(config=dev_config)

# Production: Milvus
prod_retriever = MilvusRetriever(config=prod_config)

# Cloud: Pinecone
cloud_retriever = PineconeRetriever(config=cloud_config)

# Same interface, different optimizations
for retriever in [dev_retriever, prod_retriever, cloud_retriever]:
    await retriever.initialize()
    await retriever.set_collection("documents")
    results = await retriever.get_relevant_context("search query")
    # Process results identically
```

## Design Principles

**Single Responsibility**: Each class has one clear purpose
**Open/Closed**: Open for extension, closed for modification
**Liskov Substitution**: All vector retrievers work interchangeably
**Interface Segregation**: Clean abstract interfaces
**Dependency Inversion**: Depend on abstractions, not concretions

## Integration with Adapter System

The vector retrievers work seamlessly with the existing adapter system:

```yaml
adapters:
  - name: "qa-vector"
    type: "retriever"
    datasource: "chroma"  # or "milvus", "pinecone", etc.
    adapter: "qa"
    implementation: "retrievers.implementations.qa_chroma_retriever.QAChromaRetriever"
    config:
      confidence_threshold: 0.3
```

This allows the same domain logic (QA, Legal, Medical, etc.) to work across different vector databases, providing maximum flexibility and reusability. 