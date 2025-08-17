# Vector Retriever Architecture Guide

The `AbstractVectorRetriever` architecture is designed to be **database-agnostic** and supports any vector database. The base class provides common functionality while allowing for database-specific optimizations and domain specializations.

## Architecture Hierarchy

```
BaseRetriever (abstract base for all retrievers)
└── AbstractVectorRetriever (database-agnostic vector functionality)
    ├── vector/
    │   ├── ChromaRetriever
    │   ├── QdrantRetriever
    │   ├── MilvusRetriever
    │   ├── PineconeRetriever
    │   ├── ElasticsearchRetriever
    │   └── RedisRetriever
    └── qa/
        ├── QAChromaRetriever (QA domain specialization of ChromaDB)
        └── QAQdrantRetriever (QA domain specialization of Qdrant)
```

## Supported Vector Databases

| Database | Implementation | Status | Special Features | Domain Specializations |
|:---|:---|:---|:---|:---|
| **ChromaDB** | `vector.ChromaRetriever` | ✅ Complete | Local & remote, L2 distance | `qa.QAChromaRetriever` |
| **Qdrant** | `vector.QdrantRetriever` | ✅ Complete | REST API, multiple metrics | `qa.QAQdrantRetriever` |
| **Milvus** | `vector.MilvusRetriever` | ✅ Complete | Multiple metrics (IP, L2, COSINE) | *Easy to add* |
| **Pinecone** | `vector.PineconeRetriever` | ✅ Complete | Managed cloud, similarity scores | *Easy to add* |
| **Elasticsearch** | `vector.ElasticsearchRetriever` | ✅ Complete | KNN search, text + vector | *Easy to add* |
| **Redis** | `vector.RedisRetriever` | ✅ Complete | RedisSearch, multiple metrics | *Easy to add* |

### Separation of Concerns

-   **Database Logic**: Handled by concrete classes like `ChromaRetriever`, `QdrantRetriever`, etc.
-   **Domain Logic**: Handled by specializations like `QAChromaRetriever`.
-   **Common Logic**: Handled by the `AbstractVectorRetriever` base class.

### Extensibility

-   **New Vector Databases**: Easily add support for a new database by extending `AbstractVectorRetriever`.
-   **New Domains**: Create new domain specializations (e.g., `LegalPineconeRetriever`) by extending any concrete database implementation.

## Configuration

Vector retrievers are configured in `config/adapters.yaml`. Here are some examples.

```yaml
# config/adapters.yaml

adapters:
  # ChromaDB with QA specialization
  - name: "qa-vector-chroma"
    enabled: false
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAChromaRetriever"
    config:
      collection: "city"
      confidence_threshold: 0.3
      distance_scaling_factor: 200.0

  # Qdrant with QA specialization
  - name: "qa-vector-qdrant-city"
    enabled: false
    type: "retriever"
    datasource: "qdrant"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAQdrantRetriever"
    config:
      collection: "city"
      confidence_threshold: 0.3
      score_scaling_factor: 200.0

  # Generic Pinecone adapter
  - name: "general-pinecone"
    type: "retriever"
    datasource: "pinecone"
    adapter: "generic"
    implementation: "retrievers.implementations.vector.PineconeRetriever"
    config:
      confidence_threshold: 0.5
      # Pinecone-specific config...
      api_key: "${PINECONE_API_KEY}"
      host: "https://index-name.pinecone.io"
```

## Creating New Vector Database Support

Adding support for a new vector database like Weaviate is straightforward.

### Step 1: Inherit from AbstractVectorRetriever

```python
# retrievers/implementations/vector/weaviate_retriever.py
from retrievers.base.abstract_vector_retriever import AbstractVectorRetriever

class WeaviateRetriever(AbstractVectorRetriever):
    def _get_datasource_name(self) -> str:
        return 'weaviate'
```

### Step 2: Implement Abstract Methods

Implement the methods for client initialization, collection management, and the actual vector search.

```python
    async def initialize_client(self) -> None:
        import weaviate
        self.client = weaviate.Client(url=self.host)

    async def close_client(self) -> None:
        # Weaviate client does not require explicit closing
        pass

    async def set_collection(self, collection_name: str) -> None:
        self.collection_name = collection_name
        # Verification logic here...

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        results = self.client.query.get(self.collection_name, ["content", "metadata"])
            .with_near_vector({"vector": query_embedding})
            .with_limit(top_k)
            .do()
        # Conversion logic here...
        return formatted_results
```

### Step 3: Handle Distance/Score Conversion

Implement the logic to convert the database's native search score into a normalized confidence score.

```python
    def calculate_similarity_from_distance(self, distance: float) -> float:
        # Weaviate can return distance or similarity, handle accordingly
        return float(distance)
```

### Step 4: Register with Factory

Make the new retriever available to the application.

```python
# At the end of weaviate_retriever.py
from retrievers.base.base_retriever import RetrieverFactory
RetrieverFactory.register_retriever('weaviate', WeaviateRetriever)
```

## Distance Metrics and Similarity

Different vector databases use different distance metrics. The architecture handles this by requiring each retriever to implement `calculate_similarity_from_distance`.

| Database | Metric | Conversion | Notes |
|:---|:---|:---|:---|
| **ChromaDB** | L2 Distance | `1.0 / (1.0 + distance/scale)` | Lower distance = higher similarity |
| **Qdrant** | Similarity Score | Direct use | Already a normalized similarity score |
| **Milvus** | IP/L2/COSINE | Metric-specific | Handles all three metrics |
| **Pinecone** | Similarity Score | Direct use | Already a normalized similarity score |
| **Elasticsearch**| Similarity Score | Direct use | KNN returns similarity |
| **Redis** | Distance/Score | Metric-specific | Depends on configuration |