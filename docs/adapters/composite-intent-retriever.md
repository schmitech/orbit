# Composite Intent Retriever Architecture

This document describes the Composite Intent Retriever, a specialized retriever that routes queries across multiple intent adapters to find the best matching data source for each query.

## Overview

The Composite Intent Retriever acts as a **smart router** that searches across the template stores of multiple child intent adapters, finds the best matching template regardless of which data source it belongs to, and routes the query execution to the appropriate child adapter.

This enables powerful multi-source data exploration where users can ask questions across heterogeneous data sources (SQL databases, NoSQL databases, HTTP APIs) using a single unified interface.

### Key Features

- **Cross-Source Template Matching**: Searches templates from all configured child adapters in parallel
- **Best-Match Routing**: Routes queries to the single adapter with the highest-scoring template match
- **Shared Embedding**: Uses a single embedding client for consistent similarity scoring across sources
- **Transparent Metadata**: Enriches results with routing metadata showing which source was selected
- **Configurable Behavior**: Supports parallel/sequential search, timeouts, and confidence thresholds

## Architecture

```text
                           +------------------+
                           |   User's Query   |
                           +------------------+
                                    |
                                    v
                    +-------------------------------+
                    |  CompositeIntentRetriever     |
                    |  (Smart Router)               |
                    +-------------------------------+
                                    |
              Generate Query Embedding (once)
                                    |
         +-------------+------------+-------------+
         |             |            |             |
         v             v            v             v
   +-----------+ +-----------+ +-----------+ +-----------+
   | Template  | | Template  | | Template  | | Template  |
   | Store 1   | | Store 2   | | Store 3   | | Store N   |
   | (SQLite)  | | (DuckDB)  | | (MongoDB) | | (HTTP)    |
   +-----------+ +-----------+ +-----------+ +-----------+
         |             |            |             |
         +-------------+------------+-------------+
                       |
                       v
              +------------------+
              | Rank All Matches |
              | Select Best One  |
              +------------------+
                       |
                       v
              +------------------+
              | Route to Winning |
              | Child Adapter    |
              +------------------+
                       |
                       v
              +------------------+
              |    Results       |
              | (with routing    |
              |  metadata)       |
              +------------------+
```

## How It Works

### 1. Query Processing Flow

1. **Embedding Generation**: The composite retriever generates a query embedding using its configured embedding provider. This single embedding is reused for all template searches to ensure consistent scoring.

2. **Parallel Template Search**: The retriever searches each child adapter's template store in parallel (configurable), collecting all matching templates with their similarity scores.

3. **Best Match Selection**: All templates from all sources are ranked by similarity score. The template with the highest score that meets the confidence threshold is selected.

4. **Query Routing**: The original query is forwarded to the child adapter that owns the selected template. That adapter performs parameter extraction, query execution, and result formatting.

5. **Result Enrichment**: The results from the child adapter are enriched with composite routing metadata before being returned.

### 2. Template Matching

Each child intent adapter maintains its own template store (vector database collection) containing embeddings of its templates. The composite retriever:

- Queries each template store with the same query embedding
- Collects up to `max_templates_per_source` matches from each source
- Filters matches below the `confidence_threshold`
- Sorts all matches by similarity score (highest first)
- Selects the top match for routing

### 3. Routing Decision

The routing decision is deterministic: the template with the highest similarity score wins. In case of ties, the first adapter in the configuration order is preferred.

## Configuration

### Basic Configuration

```yaml
adapters:
  - name: "composite-multi-source"
    enabled: true
    type: "retriever"
    adapter: "composite"
    implementation: "retrievers.implementations.composite.CompositeIntentRetriever"

    # Shared embedding provider for consistent scoring across sources
    embedding_provider: "openai"

    config:
      # List of child adapter names to search across
      child_adapters:
        - "intent-sql-sqlite-hr"
        - "intent-duckdb-ev-population"
        - "intent-mongodb-mflix"

      # Minimum similarity score to consider a match
      confidence_threshold: 0.4

      # Maximum templates to retrieve from each child adapter
      max_templates_per_source: 3

      # Whether to search all sources in parallel
      parallel_search: true

      # Timeout for template search per source (seconds)
      search_timeout: 5.0

      # Enable verbose logging for debugging
      verbose: false
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `child_adapters` | List[str] | Required | Names of child intent adapters to search across |
| `confidence_threshold` | float | 0.4 | Minimum similarity score to consider a template match |
| `max_templates_per_source` | int | 3 | Maximum templates to retrieve from each child adapter |
| `parallel_search` | bool | true | Whether to search all sources in parallel |
| `search_timeout` | float | 5.0 | Timeout in seconds for each template search |
| `verbose` | bool | false | Enable detailed logging of routing decisions |

### Embedding Provider Configuration

The composite retriever uses a shared embedding provider to ensure consistent similarity scoring across all child adapters. This is configured at the adapter level:

```yaml
embedding_provider: "openai"
embedding_model: "text-embedding-3-small"  # Optional
```

It's recommended to use the same embedding provider that the child adapters use for their templates, or a compatible one with similar vector dimensions.

## Child Adapter Requirements

Child adapters must be existing intent adapters (from `config/adapters/intent.yaml`) that have:

1. **A template store**: Vector database collection containing template embeddings
2. **A domain adapter**: For retrieving template definitions by ID
3. **A `get_relevant_context()` method**: For query execution

Supported child adapter types include:

| Child Adapter Type | Implementation |
|--------------------|----------------|
| SQLite Intent | `IntentSQLiteRetriever` |
| PostgreSQL Intent | `IntentPostgreSQLRetriever` |
| DuckDB Intent | `IntentDuckDBRetriever` |
| MongoDB Intent | `IntentMongoDBRetriever` |
| Elasticsearch Intent | `IntentElasticsearchRetriever` |
| HTTP/JSON Intent | `IntentHTTPJSONRetriever` |
| GraphQL Intent | `IntentGraphQLRetriever` |
| Firecrawl Intent | `IntentFirecrawlRetriever` |

## Response Format

The composite retriever returns results from the selected child adapter, enriched with routing metadata:

```json
{
  "content": "Results from the selected data source...",
  "metadata": {
    "source": "intent",
    "template_id": "ev_count_by_make",
    "composite_routing": {
      "selected_adapter": "intent-duckdb-ev-population",
      "template_id": "ev_count_by_make",
      "similarity_score": 0.92,
      "adapters_searched": [
        "intent-sql-sqlite-hr",
        "intent-duckdb-ev-population",
        "intent-mongodb-mflix"
      ],
      "total_matches_found": 7
    }
  },
  "confidence": 0.92
}
```

### Routing Metadata Fields

| Field | Description |
|-------|-------------|
| `selected_adapter` | Name of the child adapter that handled the query |
| `template_id` | ID of the template that was matched and executed |
| `similarity_score` | Confidence score of the template match |
| `adapters_searched` | List of all child adapter names that were searched |
| `total_matches_found` | Total number of template matches across all sources |

## Use Cases

### 1. Multi-Database Data Explorer

Query across multiple databases with a single interface:

```yaml
config:
  child_adapters:
    - "intent-sql-sqlite-hr"        # HR employee data
    - "intent-duckdb-analytics"     # Business analytics
    - "intent-mongodb-mflix"        # Movie catalog
```

User queries are automatically routed to the appropriate database:
- "Show me employees in the Engineering department" → HR database
- "What's the revenue trend for Q4?" → Analytics database  
- "Find movies starring Tom Hanks" → Movie catalog

### 2. Government Open Data Portal

Aggregate queries across multiple public datasets:

```yaml
config:
  child_adapters:
    - "intent-duckdb-open-gov-travel-expenses"
    - "intent-duckdb-open-gov-contracts"
    - "intent-duckdb-ottawa-police-auto-theft"
```

### 3. Hybrid SQL and API Sources

Combine traditional databases with external APIs:

```yaml
config:
  child_adapters:
    - "intent-sql-postgres-inventory"   # Internal inventory DB
    - "intent-http-pricing-api"         # External pricing API
    - "intent-mongodb-orders"           # Order history
```

## Debugging and Testing

### Test Routing Without Execution

The composite retriever provides a `test_routing()` method to debug routing decisions without actually executing queries:

```python
# Available via the adapter's test_routing method
result = await composite_adapter.test_routing("Show me all Tesla vehicles")

# Returns:
{
  "query": "Show me all Tesla vehicles",
  "total_matches": 5,
  "matches_above_threshold": 3,
  "all_matches": [
    {
      "template_id": "ev_count_by_make",
      "source_adapter": "intent-duckdb-ev-population",
      "similarity_score": 0.92,
      "description": "Count electric vehicles by make",
      "above_threshold": true
    },
    ...
  ],
  "routing_decision": {
    "would_route_to": "intent-duckdb-ev-population",
    "selected_template": "ev_count_by_make",
    "selection_score": 0.92,
    "reason": "highest_score_above_threshold"
  }
}
```

### Get Routing Statistics

```python
stats = await composite_adapter.get_routing_statistics()

# Returns:
{
  "child_adapter_count": 3,
  "child_adapters": {
    "intent-sql-sqlite-hr": {
      "total_templates": 12,
      "collection_name": "hr_intent_templates"
    },
    "intent-duckdb-ev-population": {
      "total_templates": 8,
      "collection_name": "ev_population_templates"
    },
    ...
  },
  "configuration": {
    "confidence_threshold": 0.4,
    "max_templates_per_source": 3,
    "parallel_search": true,
    "search_timeout": 5.0
  }
}
```

### Verbose Logging

Enable verbose mode to see detailed routing decisions in the logs:

```yaml
config:
  verbose: true
```

This produces logs like:

```
[Composite] Processing query: 'Show me all Tesla vehicles'
[Composite] Searching across 3 adapters: ['intent-sql-sqlite-hr', 'intent-duckdb-ev-population', 'intent-mongodb-mflix']
[Composite] Routed to: intent-duckdb-ev-population
[Composite] Template: ev_count_by_make
[Composite] Score: 0.920
[Composite] Total matches: 5
```

## Performance Considerations

### Parallel vs Sequential Search

By default, the composite retriever searches all child template stores in parallel. This provides the best performance when:

- Child adapters are on different servers/services
- Network latency varies between sources
- You have many child adapters

Sequential search (`parallel_search: false`) may be preferred when:

- All template stores are on the same server
- You want deterministic search order
- Debugging routing issues

### Search Timeout

The `search_timeout` parameter prevents slow sources from blocking the entire search:

```yaml
config:
  search_timeout: 5.0  # 5 seconds per source
```

If a child adapter's template search exceeds this timeout, it's skipped and the composite continues with results from other sources.

### Template Store Size

The composite retriever only fetches `max_templates_per_source` templates from each child. This keeps memory usage bounded even with many child adapters:

```
Total templates fetched = num_child_adapters × max_templates_per_source
```

## Limitations

1. **Single Source Execution**: Only the best-matching source executes the query. Results are not merged from multiple sources.

2. **Shared Embedding Requirement**: All child adapters should ideally use the same embedding model, or the similarity scores may not be directly comparable.

3. **Child Adapter Initialization**: Child adapters must be fully initialized before the composite retriever can use them. The composite does not initialize child adapters.

4. **No Cross-Source Joins**: The composite retriever cannot join data across sources. Each query goes to exactly one source.

## Implementation Details

### Class Hierarchy

```
BaseRetriever
    └── CompositeIntentRetriever (base class)
            └── CompositeIntentRetriever (implementation)
```

### Key Files

| File | Purpose |
|------|---------|
| `server/retrievers/base/intent_composite_base.py` | Base class with core routing logic |
| `server/retrievers/implementations/composite/composite_intent_retriever.py` | Full implementation with debug methods |
| `config/adapters/composite.yaml` | Example configurations |

### Data Structures

```python
@dataclass
class TemplateMatch:
    """Represents a template match from a child adapter."""
    template_id: str          # Unique template identifier
    source_adapter: str       # Name of the child adapter
    similarity_score: float   # Embedding similarity score
    template_data: Dict       # Full template definition
    embedding_text: str       # Text used for embedding
```

## Related Documentation

- [Adapters Overview](./adapters.md) - General adapter architecture
- [Adapter Configuration](./adapter-configuration.md) - Configuration management
- [Intent-SQL RAG System](../intent-sql-rag-system.md) - Intent adapter internals

