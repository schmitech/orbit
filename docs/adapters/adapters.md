# ORBIT Retriever Adapter Architecture

This guide explains the adapter-based architecture for data retrieval in ORBIT. The architecture is designed to be modular, configuration-driven, and easily extensible, allowing seamless integration of various data sources and retrieval strategies.

## Core Concepts

The retriever architecture is built on a few key concepts that work together to provide a flexible and powerful data retrieval system.

### 1. Adapter Configuration (`adapters.yaml`)

The entire retriever system is driven by the `config/adapters.yaml` file. This file defines all the available "adapters," which are pre-configured retriever instances. The application loads these configurations at startup.

Each adapter definition has the following key properties:

- `name`: A unique name for the adapter instance (e.g., `qa-sql`).
- `enabled`: A boolean to enable or disable the adapter.
- `type`: The type of component, which is `"retriever"` for all retrievers.
- `datasource`: The underlying data source type (e.g., `sqlite`, `qdrant`, `postgres`). This determines which base retriever implementation is used.
- `adapter`: The domain-specific adapter to use (e.g., `qa`, `intent`). This controls how data is processed and interpreted.
- `implementation`: The full Python path to the retriever's implementation class (e.g., `retrievers.implementations.qa.QASSQLRetriever`).
- `config`: A dictionary of settings specific to this adapter instance, such as confidence thresholds, collection names, or feature flags.

### 2. Retriever Implementations

A Retriever is a class responsible for connecting to a data source and fetching data. ORBIT provides several base classes that new retrievers can extend:

- `AbstractVectorRetriever`: The base for retrievers that connect to vector databases (Chroma, Qdrant, etc.).
- `AbstractSQLRetriever`: The base for retrievers that connect to SQL databases.
- `IntentSQLRetriever`: A specialized base for building powerful text-to-SQL retrievers.

These base classes handle common logic, allowing implementations to focus on the specifics of the data source they support.

### 3. Domain Adapters

A Domain Adapter is a component that provides the domain-specific logic for a retriever. It handles tasks like:

- Formatting documents for a specific use case (e.g., question-answering).
- Applying domain-specific filtering or ranking to results.
- Extracting direct answers from the retrieved context.

The `adapter` key in the configuration determines which domain adapter is plugged into the retriever. This allows the same retriever implementation (e.g., `QdrantRetriever`) to be used for different purposes just by changing the configuration.

### 4. Adapter Registry

The `AdapterRegistry` is a central, in-code component that manages the lifecycle of all adapters. At startup, it reads the `adapters.yaml` file and registers all enabled adapters. When the application needs to perform a retrieval, it requests an adapter by name from the registry, which then instantiates and returns the correctly configured retriever.

## Architecture Diagram

The following diagram illustrates the flow of a request through the retriever adapter architecture:

```text
      +------------------+
      |   User's Query   |
      +------------------+
               |
               v
      +------------------+
      | ORBIT Application|
      +------------------+
               |
               | Requests adapter by name (e.g., "qa-sql")
               v
      +------------------+
      | Adapter Registry |
      +------------------+
               |
               | 1. Reads config from `adapters.yaml`
               | 2. Creates the configured Retriever Implementation
               v
+--------------------------------------------------------------------------+
|                                                                          |
|  Retriever Implementation (e.g., `QASSQLRetriever`)                      |
|                                                                          |
|  +--------------------------------+      +-----------------------------+ |
|  |                                |      |                             | |
|  |         Domain Adapter         |----->|        Data Source          | |
|  | (e.g., `QADocumentAdapter`)    |      | (e.g., SQLite Connection)   | |
|  |                                |      |                             | |
|  | - Formats data for the domain  |      | - Fetches raw data          | |
|  | - Applies domain-specific logic|      |                             | |
|  |                                |      |                             | |
|  +--------------------------------+      +-----------------------------+ |
|                                                                          |
+--------------------------------------------------------------------------+
               |
               | Returns formatted, domain-specific results
               v
      +------------------+
      |     Response     |
      +------------------+
```

## Architecture Strengths

This architecture provides several significant advantages:

1.  **Clear Separation of Concerns**: Base retrievers handle data source communication, while domain adapters handle use-case-specific logic. This keeps the code clean and organized.
2.  **Configuration-Driven**: The behavior of the retrieval system can be changed entirely through YAML configuration without touching any code, making it easy to experiment and deploy new configurations.
3.  **Extensibility**: Adding support for a new database or a new use case is straightforward. You can create a new retriever implementation or a new domain adapter and register it in the configuration.
4.  **Reusability**: The same retriever implementation can be reused across multiple adapters for different domains, reducing code duplication.
5.  **Lazy Loading**: Components are loaded and initialized on-demand, which improves startup time and reduces memory usage.

## Available Implementations

ORBIT comes with a variety of pre-built retriever implementations and domain adapters.

### Retriever Implementations

| Category | Class Name | Datasource | Description |
| :--- | :--- | :--- | :--- |
| **QA (Vector)** | `QAChromaRetriever` | `chroma` | Specialized for QA over ChromaDB. |
| | `QAQdrantRetriever` | `qdrant` | Specialized for QA over Qdrant. |
| **QA (SQL)** | `QASSQLRetriever` | `sqlite` | Specialized for QA over SQLite using text similarity. |
| **Intent (SQL)** | `IntentPostgreSQLRetriever` | `postgres` | A powerful text-to-SQL retriever for PostgreSQL. |
| | `IntentMySQLRetriever` | `mysql` | A powerful text-to-SQL retriever for MySQL. |
| **Intent (Agent)** | `IntentAgentRetriever` | `http` | Extends intent retrieval with function calling and tool execution. |
| **Composite** | `CompositeIntentRetriever` | multiple | Routes queries across multiple intent adapters to find the best matching source. |
| **Generic Vector**| `ChromaRetriever` | `chroma` | Generic retriever for ChromaDB. |
| | `QdrantRetriever` | `qdrant` | Generic retriever for Qdrant. |
| | `MilvusRetriever` | `milvus` | Generic retriever for Milvus. |
| | `PineconeRetriever` | `pinecone` | Generic retriever for Pinecone. |
| | `ElasticsearchRetriever`| `elasticsearch`| Generic retriever for Elasticsearch. |
| | `RedisRetriever` | `redis` | Generic retriever for Redis (with RedisSearch). |
| **Generic SQL** | `SQLiteRetriever` | `sqlite` | Generic retriever for SQLite. |
| | `PostgreSQLRetriever` | `postgres` | Generic retriever for PostgreSQL. |
| | `MySQLRetriever` | `mysql` | Generic retriever for MySQL. |

### Domain Adapters

| Name (`adapter`) | Class Name | Description |
| :--- | :--- | :--- |
| `qa` | `QADocumentAdapter` | Formats documents for question-answering tasks. |
| `intent` | `IntentAdapter` | Manages domain knowledge and templates for text-to-SQL translation. |
| `intent` (agent) | `IntentAgentRetriever` | Extends intent adapter with function calling and built-in tool execution. |
| `composite` | N/A (uses child adapters) | Routes queries to child adapters; delegates formatting to the selected child. |
| `generic` | `GenericDocumentAdapter` | Provides basic, general-purpose document formatting. |

## Configuration Examples

Here are some examples from `config/adapters.yaml` that show how to configure different types of retrievers.

### Example 1: QA over SQL (SQLite)

This adapter uses the `QASSQLRetriever` to perform question-answering over a local SQLite database. It uses the `qa` domain adapter.

```yaml
- name: "qa-sql"
  enabled: true
  type: "retriever"
  datasource: "sqlite"
  adapter: "qa"
  implementation: "retrievers.implementations.qa.QASSQLRetriever"
  config:
    confidence_threshold: 0.3
    max_results: 5
    table: "city"
```

### Example 2: QA over Vector (Qdrant)

This adapter uses the `QAQdrantRetriever` to perform QA over a Qdrant vector database.

```yaml
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
    embedding_provider: null
    max_results: 5
```

### Example 4: Intent-to-SQL (PostgreSQL)

This adapter uses the `IntentPostgreSQLRetriever` to translate natural language questions into SQL queries for a PostgreSQL database.

```yaml
- name: "intent-sql-postgres"
  enabled: false
  type: "retriever"
  datasource: "postgres"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentPostgreSQLRetriever"
  config:
    domain_config_path: "config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml"
    template_library_path: 
      - "config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml"
    confidence_threshold: 0.75
    max_templates: 5
```

## Extending the Architecture

You can easily extend ORBIT with your own custom retrievers and domain adapters.

### Creating a New Retriever Implementation

1.  **Create a new class** that extends one of the base retriever classes (e.g., `AbstractVectorRetriever` or `BaseSQLDatabaseRetriever`).
2.  **Implement the required abstract methods**, such as `_get_datasource_name`, `initialize_client`, `close_client`, and `vector_search` (for vector DBs) or `create_connection` and `_execute_raw_query` (for SQL DBs).
3.  **Place your implementation** in the `server/retrievers/implementations/` directory.
4.  **Add a new entry** in `config/adapters.yaml` pointing to your new implementation class.

### Creating a New Domain Adapter

1.  **Create a new class** that extends `DocumentAdapter`.
2.  **Implement the required methods**: `format_document()`, `extract_direct_answer()`, and `apply_domain_specific_filtering()`.
3.  **Register the adapter** with the `DocumentAdapterFactory` so it can be referenced by the `adapter` key in the configuration. This is typically done at the bottom of the adapter's file.

Example registration:
```python
# In your_adapter.py
from adapters.factory import DocumentAdapterFactory

# ... your adapter class definition ...

# Register with the factory
DocumentAdapterFactory.register_adapter("your_adapter_name", YourAdapterClass)
```

## Detailed Documentation

For more in-depth information on specific retriever types, see the following guides:

-   **[Vector Retriever Architecture Guide](./vector-retriever-architecture.md)**: A guide for developers working with vector databases. It covers the architecture, supported databases, and how to add new ones.

-   **[SQL Retriever Architecture & Implementation Guide](./sql-retriever-architecture.md)**: A guide for developers working with any SQL-based retriever. It covers architecture, configuration, best practices, and how to add support for new SQL databases.

-   **[Intent-SQL RAG System](./intent-sql-rag-system.md)**: A deep-dive into the powerful Intent-to-SQL system, explaining how to configure and extend it for any business domain.

-   **[Composite Intent Retriever](./composite-intent-retriever.md)**: A guide to the composite retriever that routes queries across multiple intent adapters to find the best matching data source.

-   **[Intent Agent Retriever](./intent-agent-retriever.md)**: A guide to the agent retriever that extends intent-based retrieval with function calling, tool execution, and response synthesis.
