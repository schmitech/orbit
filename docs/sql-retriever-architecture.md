# SQL & Structured Data Retriever Architecture

This guide provides a comprehensive overview of the SQL and structured data retriever architecture in ORBIT. The system supports traditional SQL databases, analytical engines like DuckDB, NoSQL databases like MongoDB, and HTTP-based APIs—all through a unified interface with optional intent-based natural language querying.

## Architecture Overview

The retriever system follows a layered architecture with clear separation of concerns:

```
BaseRetriever (abstract base for all retrievers)
├── AbstractSQLRetriever (traditional SQL functionality)
│   └── BaseSQLDatabaseRetriever (unified SQL with mixins)
│       ├── relational/
│       │   ├── SQLiteRetriever
│       │   ├── PostgreSQLRetriever
│       │   └── MySQLRetriever
│       └── qa/
│           └── QASSQLRetriever (QA domain specialization)
│
├── IntentSQLRetriever (intent-based SQL, extends BaseSQLDatabaseRetriever)
│   ├── IntentSQLiteRetriever
│   ├── IntentPostgreSQLRetriever
│   ├── IntentMySQLRetriever
│   └── IntentDuckDBRetriever
│
├── IntentHTTPRetriever (intent-based HTTP queries)
│   ├── IntentHTTPJSONRetriever (REST APIs)
│   ├── IntentElasticsearchRetriever (Elasticsearch Query DSL)
│   ├── IntentMongoDBRetriever (MongoDB aggregation pipelines)
│   ├── IntentGraphQLRetriever (GraphQL queries)
│   └── IntentFirecrawlRetriever (web scraping)
│
└── AbstractVectorRetriever (vector similarity search)
    ├── ChromaRetriever, PineconeRetriever, QdrantRetriever
    ├── MilvusRetriever, ElasticsearchRetriever, RedisRetriever
    └── qa/ (QA specializations for vector stores)
```

### Two Retriever Paradigms

ORBIT supports two retriever paradigms:

| Paradigm | Description | Use Case |
|:---|:---|:---|
| **Traditional** | Direct SQL/API queries with explicit parameters | Programmatic access, fixed queries |
| **Intent-Based** | Natural language → query translation using LLMs and templates | Conversational AI, dynamic queries |

## Supported Databases & APIs

### SQL & SQL-Like Databases

| Database | Traditional Implementation | Intent Implementation | Status | Special Features |
|:---|:---|:---|:---|:---|
| **SQLite** | `relational.SQLiteRetriever` | `intent.IntentSQLiteRetriever` | ✅ Complete | File-based, FTS5 support |
| **PostgreSQL** | `relational.PostgreSQLRetriever` | `intent.IntentPostgreSQLRetriever` | ✅ Complete | Full-text search, JSON ops |
| **MySQL** | `relational.MySQLRetriever` | `intent.IntentMySQLRetriever` | ✅ Complete | FULLTEXT indexes |
| **DuckDB** | — | `intent.IntentDuckDBRetriever` | ✅ Complete | Analytics, Parquet/CSV, columnar |

### NoSQL & Document Databases

| Database | Intent Implementation | Status | Special Features |
|:---|:---|:---|:---|
| **MongoDB** | `intent.IntentMongoDBRetriever` | ✅ Complete | Aggregation pipelines, text search |
| **Elasticsearch** | `intent.IntentElasticsearchRetriever` | ✅ Complete | Query DSL, aggregations |

### HTTP-Based APIs

| API Type | Intent Implementation | Status | Special Features |
|:---|:---|:---|:---|
| **REST JSON** | `intent.IntentHTTPJSONRetriever` | ✅ Complete | JSON APIs, auth support |
| **GraphQL** | `intent.IntentGraphQLRetriever` | ✅ Complete | Query generation |
| **Firecrawl** | `intent.IntentFirecrawlRetriever` | ✅ Complete | Web scraping, content chunking |

## Base Class Features

### BaseSQLDatabaseRetriever

The unified SQL base class (`retrievers/base/base_sql_database.py`) provides:

- **Environment Variable Support**: Use `${VAR_NAME}` or `${VAR_NAME:default_value}` in configuration
- **Connection Management**: Built-in pooling and automatic reconnection on transient failures
- **Type Conversion**: Automatic conversion of Decimal, datetime, UUID, memoryview to standard Python types
- **Query Monitoring**: Logs slow queries and large result sets when debug logging is enabled
- **Mixins for Reusability**:
  - `SQLConnectionMixin`: Environment variable resolution, connection parameter extraction
  - `SQLTypeConversionMixin`: Database type → Python type conversion
  - `SQLQueryExecutionMixin`: Retry logic, result file dumping

### IntentSQLRetriever

The intent-based SQL retriever (`retrievers/base/intent_sql_base.py`) adds:

- **Template Matching**: Vector similarity search to find relevant SQL templates
- **Parameter Extraction**: LLM-based extraction of query parameters from natural language
- **Domain-Aware Components**:
  - `DomainParameterExtractor`: Extracts parameters using domain vocabulary
  - `DomainResponseGenerator`: Formats results with domain-specific styling
  - `TemplateReranker`: Re-ranks templates using domain rules
  - `TemplateProcessor`: Jinja2-like SQL template rendering

### IntentHTTPRetriever

The intent-based HTTP retriever (`retrievers/base/intent_http_base.py`) provides:

- **HTTP Client Management**: Async client with connection pooling
- **Authentication Support**: Basic auth, API key, Bearer token
- **Template-Based Queries**: HTTP request templates with parameter substitution
- **Response Processing**: JSON response parsing and formatting

## Configuration

### Adapter Configuration (config/adapters/intent.yaml)

Intent-based adapters are configured with domain and template paths:

```yaml
adapters:
  - name: "intent-duckdb-analytics"
    enabled: true
    type: "retriever"
    datasource: "duckdb"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentDuckDBRetriever"
    database: "path/to/analytics.duckdb"
    
    # Provider overrides for this adapter
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b"
    embedding_provider: "ollama"
    embedding_model: "nomic-embed-text:latest"
    
    config:
      # Domain and template configuration
      domain_config_path: "utils/duckdb-intent-template/examples/analytics/analytics_domain.yaml"
      template_library_path:
        - "utils/duckdb-intent-template/examples/analytics/analytics_templates.yaml"
      
      # Vector store for template matching
      template_collection_name: "duckdb_analytics_templates"
      store_name: "chroma"
      
      # Intent matching settings
      confidence_threshold: 0.4
      max_templates: 5
      return_results: 100
      
      # Template loading
      reload_templates_on_start: false
      force_reload_templates: false
      
      # DuckDB-specific settings
      read_only: true
      access_mode: "READ_ONLY"
      
      # Query monitoring
      enable_query_monitoring: true
      query_timeout: 5000  # milliseconds
```

### DuckDB-Specific Configuration

DuckDB adapters support analytical workloads with these options:

| Option | Description | Default |
|:---|:---|:---|
| `read_only` | Open database in read-only mode for concurrent access | `false` |
| `access_mode` | DuckDB access mode: `READ_ONLY`, `READ_WRITE`, `automatic` | `automatic` |
| `threads` | Number of threads for query execution | System default |
| `database` | Path to `.duckdb` file or `:memory:` | `:memory:` |

### MongoDB-Specific Configuration

```yaml
config:
  database: "sample_mflix"
  default_collection: "movies"
  default_limit: 100
  max_limit: 1000
  enable_text_search: true
  case_insensitive_regex: true
```

### HTTP API Configuration

```yaml
config:
  base_url: "https://api.example.com"
  default_timeout: 30
  enable_retries: true
  max_retries: 3
  retry_delay: 1.0
  
  # Authentication
  auth:
    type: "bearer_token"  # or "api_key", "basic_auth"
    token_env: "API_TOKEN"
    header_name: "Authorization"
    token_prefix: "Bearer"
```

## Intent Template System

### Domain Configuration

Each intent adapter requires a domain configuration file that defines:

```yaml
domain:
  name: "analytics"
  description: "Sales and marketing analytics"
  
vocabulary:
  entity_synonyms:
    revenue: ["sales", "income", "earnings"]
    customer: ["client", "user", "buyer"]
  
  date_patterns:
    - "last {n} days"
    - "this month"
    - "year to date"
```

### SQL Template Format

```yaml
templates:
  - id: "revenue_by_region"
    description: "Get revenue breakdown by geographic region"
    category: "analytics"
    
    nl_examples:
      - "Show me revenue by region"
      - "What are sales per territory?"
      - "Regional revenue breakdown"
    
    sql_template: |
      SELECT region, SUM(amount) as total_revenue
      FROM sales
      {% if start_date %}WHERE sale_date >= :start_date{% endif %}
      GROUP BY region
      ORDER BY total_revenue DESC
      LIMIT :limit
    
    parameters:
      - name: "start_date"
        type: "date"
        description: "Filter sales from this date"
        required: false
      - name: "limit"
        type: "integer"
        description: "Maximum results to return"
        default: 10
    
    semantic_tags:
      action: "aggregate"
      primary_entity: "revenue"
      qualifiers: ["by_region"]
```

### HTTP Template Format

```yaml
templates:
  - id: "search_events"
    description: "Search for events in Paris"
    
    nl_examples:
      - "Find concerts in Paris"
      - "What events are happening this weekend?"
    
    http_request:
      method: "GET"
      endpoint: "/api/events"
      query_params:
        q: "{{query}}"
        date_from: "{{start_date}}"
        limit: "{{limit}}"
    
    parameters:
      - name: "query"
        type: "string"
        description: "Search term"
        required: true
```

## Best Practices

### ✅ Recommended Patterns

1. **Use Intent Adapters for Conversational AI**: Intent-based retrievers translate natural language to structured queries, ideal for chat interfaces.

2. **Template Isolation**: Each adapter should have its own template collection to prevent cross-adapter template matching.

3. **Read-Only Mode for Analytics**: Use `read_only: true` for DuckDB analytics workloads to enable concurrent access.

4. **Materialized Views**: For complex aggregations, pre-compute results in materialized views.

5. **Security Filters**: Always include `security_filter` and `allowed_columns` for production deployments.

6. **Environment Variables**: Store credentials in environment variables, not in config files.

### ❌ Patterns to Avoid

1. **Open-ended JOINs**: Avoid complex joins in adapters; use materialized views.

2. **Missing LIMIT**: Always include limits to prevent runaway queries.

3. **SELECT ***: Specify columns explicitly for security and performance.

4. **Shared Template Collections**: Don't share template collections across adapters.

## Extending the Architecture

### Adding a New SQL-Like Database

1. **Create the Retriever Class**:

```python
from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory

class IntentMyNewDBRetriever(IntentSQLRetriever):
    """MyNewDB intent retriever."""
    
    def _get_datasource_name(self) -> str:
        return "mynewdb"
    
    def get_default_port(self) -> int:
        return 5432
    
    def get_default_database(self) -> str:
        return "default"
    
    def get_default_username(self) -> str:
        return "admin"
    
    async def create_connection(self) -> Any:
        # Create and return database connection
        pass
    
    def get_test_query(self) -> str:
        return "SELECT 1"
    
    async def _execute_raw_query(self, query: str, params=None) -> List[Any]:
        # Execute query and return results as list of dicts
        pass

# Register the retriever
RetrieverFactory.register_retriever('intent_mynewdb', IntentMyNewDBRetriever)
```

2. **Add Configuration**: Create domain and template YAML files.

3. **Register in `__init__.py`**: Add import to `retrievers/implementations/intent/__init__.py`.

### Adding a New HTTP-Based API

1. **Create the Retriever Class**:

```python
from retrievers.base.intent_http_base import IntentHTTPRetriever

class IntentMyAPIRetriever(IntentHTTPRetriever):
    """Custom API intent retriever."""
    
    async def _execute_template(self, template, parameters):
        # Build and execute HTTP request
        # Return (results, error)
        pass
    
    def _format_http_results(self, results, template, parameters, similarity):
        # Format results for LLM context
        pass
```

### Creating Domain Specializations

Extend an existing retriever to add domain-specific logic:

```python
from retrievers.implementations.intent import IntentDuckDBRetriever

class FinanceAnalyticsRetriever(IntentDuckDBRetriever):
    """Finance-specific DuckDB retriever with custom formatting."""
    
    def _format_sql_results(self, results, template, parameters, similarity, **kwargs):
        # Add currency formatting, fiscal year calculations, etc.
        pass
```

## Query Flow

### Intent-Based Query Processing

```
1. User Query: "Show me top customers by revenue last month"
                    ↓
2. Template Matching:
   - Generate query embedding
   - Search vector store for similar templates
   - Rerank using domain rules
                    ↓
3. Parameter Extraction:
   - LLM extracts: {limit: 10, period: "last_month"}
   - Validate against template schema
                    ↓
4. Query Execution:
   - Render SQL template with parameters
   - Execute against database
                    ↓
5. Response Formatting:
   - Format results using domain generator
   - Return structured context for LLM
```

## Fault Tolerance

All intent retrievers support fault tolerance configuration:

```yaml
fault_tolerance:
  operation_timeout: 30.0
  failure_threshold: 5
  recovery_timeout: 60.0
  max_retries: 3
  retry_delay: 1.0
  enable_exponential_backoff: true
```

## Performance Considerations

| Database | Best For | Concurrency | Notes |
|:---|:---|:---|:---|
| SQLite | Small datasets, embedded | Single writer | Use WAL mode for better concurrency |
| PostgreSQL | Production workloads | High | Use connection pooling |
| MySQL | Web applications | High | Optimize with indexes |
| DuckDB | Analytics, OLAP | Read-heavy | Use `read_only: true` for concurrent reads |
| MongoDB | Document storage | High | Use indexes on query fields |
| Elasticsearch | Full-text search | High | Tune shard/replica settings |

## Related Documentation

- [Vector Store Architecture](./vector_store_architecture.md)
- [Intent SQL/RAG System](./intent-sql-rag-system.md)
- [Datasource Pooling](./datasource-pooling.md)
- [Configuration Guide](./configuration.md)
