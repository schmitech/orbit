# Composite Intent Retriever Architecture

This document describes the Composite Intent Retriever, a specialized retriever that routes queries across multiple intent adapters to find the best matching data source for each query.

## Overview

The Composite Intent Retriever acts as a **smart router** that searches across the template stores of multiple child intent adapters, finds the best matching template regardless of which data source it belongs to, and routes the query execution to the appropriate child adapter.

This enables powerful multi-source data exploration where users can ask questions across heterogeneous data sources (SQL databases, NoSQL databases, HTTP APIs) using a single unified interface.

### Key Features

- **Cross-Source Template Matching**: Searches templates from all configured child adapters in parallel
- **Multi-Stage Selection**: Optional reranking and string similarity scoring for improved accuracy at scale
- **Best-Match Routing**: Routes queries to the single adapter with the highest-scoring template match
- **Cross-Adapter Templates**: Dedicated templates for multi-source queries (e.g., "compare sales analytics with order data") that route to multiple child adapters in parallel and merge results
- **Shared Embedding**: Uses a single embedding client for consistent similarity scoring across sources
- **Transparent Metadata**: Enriches results with routing metadata showing which source was selected
- **Configurable Behavior**: Supports parallel/sequential search, timeouts, and confidence thresholds

## Architecture

### Basic Flow (Single-Stage)

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
         +-------------+------------+-------------+------------+
         |             |            |             |            |
         v             v            v             v            v
   +-----------+ +-----------+ +-----------+ +-----------+ +-----------+
   | Template  | | Template  | | Template  | | Template  | | Cross-    |
   | Store 1   | | Store 2   | | Store 3   | | Store N   | | Adapter   |
   | (SQLite)  | | (DuckDB)  | | (MongoDB) | | (HTTP)    | | Templates |
   +-----------+ +-----------+ +-----------+ +-----------+ +-----------+
         |             |            |             |            |
         +-------------+------------+-------------+------------+
                                    |
                                    v
                           +------------------+
                           | Rank All Matches |
                           | Select Best One  |
                           +------------------+
                                    |
                        +-----------+-----------+
                        |                       |
                  cross_adapter?           single adapter
                        |                       |
                        v                       v
              +------------------+     +------------------+
              | Route to ALL     |     | Route to Winning |
              | Target Adapters  |     | Child Adapter    |
              | (parallel)       |     +------------------+
              +------------------+              |
                        |                       v
                        v              +------------------+
              +------------------+     |    Results       |
              |  Merge Results   |     | (with routing    |
              | (side_by_side or |     |  metadata)       |
              |  labeled_concat) |     +------------------+
              +------------------+
                        |
                        v
              +------------------+
              |  Merged Results  |
              | (with cross-     |
              |  adapter meta)   |
              +------------------+
```

### Multi-Stage Selection Flow (Enhanced Accuracy)

When multi-stage selection is enabled, the retriever uses a three-stage scoring pipeline:

```text
                           +------------------+
                           |   User's Query   |
                           +------------------+
                                    |
                                    v
                    +-------------------------------+
                    |  STAGE 1: Embedding Search    |
                    |  (Fast semantic matching)     |
                    +-------------------------------+
                                    |
                         Top N candidates (e.g., 10)
                                    |
                                    v
                    +-------------------------------+
                    |  STAGE 2: LLM Reranking       |
                    |  (Semantic refinement via     |
                    |   Anthropic/OpenAI/Cohere)    |
                    +-------------------------------+
                                    |
                                    v
                    +-------------------------------+
                    |  STAGE 3: String Similarity   |
                    |  (Jaro-Winkler/Levenshtein    |
                    |   lexical matching)           |
                    +-------------------------------+
                                    |
                                    v
                    +-------------------------------+
                    |  Combined Score Calculation   |
                    |  score = w1*emb + w2*rerank   |
                    |         + w3*string_sim       |
                    +-------------------------------+
                                    |
                                    v
                    +-------------------------------+
                    |  Select Best Combined Score   |
                    |  Route to Child Adapter       |
                    +-------------------------------+
```

## How It Works

### 1. Query Processing Flow

1. **Embedding Generation**: The composite retriever generates a query embedding using its configured embedding provider. This single embedding is reused for all template searches to ensure consistent scoring.

2. **Parallel Template Search**: The retriever searches each child adapter's template store in parallel (configurable), collecting all matching templates with their similarity scores. If cross-adapter templates are enabled, their template store is also searched and results are merged into the same candidate list.

3. **Best Match Selection**: All templates from all sources (including cross-adapter templates) are ranked by similarity score. The template with the highest score that meets the confidence threshold is selected.

4. **Query Routing**: 
   - **Single-adapter match**: The original query is forwarded to the child adapter that owns the selected template. That adapter performs parameter extraction, query execution, and result formatting.
   - **Cross-adapter match**: The query is sent to all target adapters defined in the cross-adapter template in parallel. Results from each adapter are merged according to the template's merge strategy.

5. **Result Enrichment**: The results are enriched with composite routing metadata before being returned. Cross-adapter results include additional metadata identifying which adapters succeeded or failed.

### 2. Template Matching

Each child intent adapter maintains its own template store (vector database collection) containing embeddings of its templates. Child adapters using per-example indexing (all SQL/DuckDB intent adapters) store multiple vectors per template — one per `nl_example` — with IDs like `template_id::ex0`, `template_id::ex1`. The composite retriever handles this transparently:

- Queries each template store with the same query embedding (over-fetching by 3x to account for per-example duplicates)
- **Deduplicates per-example vectors**: strips `::exN` suffixes and keeps only the highest-scoring hit per base template
- Trims to `max_templates_per_source` deduplicated matches per source
- Filters matches below the `confidence_threshold`
- Sorts all matches by similarity score (highest first)
- Selects the top match for routing

### 3. Routing Decision

The routing decision is deterministic: the template with the highest similarity score (or combined score when multi-stage is enabled) wins. In case of ties, the configured `tie_breaker` strategy is used (default: `"embedding"` — the raw embedding score breaks the tie).

## Multi-Stage Selection

As the number of templates grows across multiple business domains, embedding similarity alone may not distinguish between templates with overlapping vocabulary (e.g., "show all employees" vs "show all customers"). Multi-stage selection addresses this by combining three complementary scoring methods.

### Why Multi-Stage Selection?

| Problem | Solution |
|---------|----------|
| Similar embeddings for different domains | LLM reranker understands semantic context |
| Typos or slight variations in queries | String similarity handles lexical variations |
| False positives from embedding search | Multiple scoring signals reduce errors |

### Scoring Stages

#### Stage 1: Embedding Search (Always Active)
- Fast vector similarity search across all template stores
- Returns top N candidates (default: 10) for further scoring
- Score range: 0.0 - 1.0

#### Stage 2: LLM Reranking (Optional)
- Uses configured reranker (Anthropic, OpenAI, Cohere, etc.)
- Compares query against template descriptions and nl_examples
- Better semantic understanding than embedding alone
- Only the top N candidates (default: 10) are sent to the reranker; candidates beyond N use their embedding score as a proxy to avoid a score cliff at the cutoff boundary
- Score range: 0.0 - 1.0

#### Stage 3: String Similarity (Optional)
- Algorithms: `jaro_winkler` (recommended), `levenshtein`, or `ratio`
- Compares query against template fields (description, nl_examples)
- Catches lexical matches that embeddings miss
- Score range: 0.0 - 1.0

### Combined Score Calculation

```
combined_score = (embedding_weight × embedding_score)
               + (reranking_weight × rerank_score)
               + (string_similarity_weight × string_sim_score)
```

Default weights (configurable):
- Embedding: 0.4
- Reranking: 0.4
- String Similarity: 0.2

### Example: Multi-Stage in Action

Query: "Show me all employees in Engineering"

| Template | Embedding | Rerank | String Sim | Combined |
|----------|-----------|--------|------------|----------|
| `employee_by_department` (HR) | 0.89 | 0.95 | 0.78 | **0.89** |
| `customer_by_region` (Sales) | 0.87 | 0.45 | 0.32 | 0.59 |
| `show_all_members` (MongoDB) | 0.85 | 0.52 | 0.41 | 0.61 |

Without multi-stage, `customer_by_region` might have been selected (0.87 vs 0.89 is close). With multi-stage, the reranker and string similarity clearly identify `employee_by_department` as the correct match.

### Multi-Stage Configuration

Multi-stage selection is configured globally in `config.yaml`:

```yaml
composite_retrieval:
  # Stage 2: LLM Reranking
  reranking:
    enabled: true              # Enable/disable reranking stage
    provider: "anthropic"      # Reranker from rerankers.yaml
    top_candidates: 10         # Max candidates to rerank
    weight: 0.4                # Weight in combined score

  # Stage 3: String Similarity
  string_similarity:
    enabled: true              # Enable/disable string similarity
    algorithm: "jaro_winkler"  # Options: jaro_winkler, levenshtein, ratio
    weight: 0.2                # Weight in combined score
    compare_fields:            # Template fields to compare
      - "description"
      - "nl_examples"
    min_threshold: 0.3         # Minimum similarity to consider
    aggregation: "max"         # How to combine multiple field scores

  # Combined scoring
  scoring:
    embedding_weight: 0.4      # Weight for Stage 1
    normalize_scores: true     # Normalize all scores to 0-1
    tie_breaker: "embedding"   # Tie-breaker strategy

  # Performance
  performance:
    parallel_rerank: true      # Rerank in parallel batches
    cache_rerank_results: true # Cache reranking results
    cache_ttl_seconds: 300     # Cache TTL (5 minutes)
```

### Performance Considerations

| Stage | Latency | Cost |
|-------|---------|------|
| Embedding Search | ~50-100ms | Free (local) |
| LLM Reranking | ~200-500ms | API cost per query |
| String Similarity | ~5-20ms | Free (local) |

**Recommendations:**
- For <50 templates: Embedding-only may suffice
- For 50-200 templates: Enable string similarity
- For 200+ templates: Enable both reranking and string similarity

## Cross-Adapter Templates

Cross-adapter templates enable multi-source queries -- queries that need data from more than one child adapter. For example, "compare sales analytics with order data" requires results from both the analytics adapter and the orders adapter.

### How Cross-Adapter Templates Work

1. Cross-adapter templates are defined in separate YAML files and owned by the composite retriever (not by any child adapter).
2. During initialization, the composite retriever embeds the `nl_examples` from cross-adapter templates into a dedicated vector store collection.
3. At query time, cross-adapter templates compete in the same scoring pipeline as child adapter templates. The best overall match wins.
4. If a cross-adapter template wins, the composite retriever routes the query to **all target adapters** in parallel and merges the results.
5. If a regular child adapter template wins, the existing single-adapter routing path is used (unchanged).

### Cross-Adapter Template Format

```yaml
templates:
  - id: compare_sales_and_orders
    description: Compare sales analytics data with order records from different databases
    cross_adapter: true
    target_adapters:
      - adapter: "intent-duckdb-analytics"
        label: "Sales Analytics"
      - adapter: "intent-sql-postgres"
        label: "Orders"
    merge_strategy: side_by_side
    partial_results: true
    nl_examples:
      - "compare sales analytics with order data"
      - "show me both sales trends and recent orders"
      - "how do analytics sales compare with actual orders"
    tags:
      - comparison
      - cross-source
      - sales
      - orders
```

#### Template Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique template identifier |
| `description` | string | Yes | Human-readable description (also used for embedding context) |
| `cross_adapter` | bool | Yes | Must be `true` |
| `target_adapters` | list | Yes | Child adapters to query (minimum 2). Each entry has `adapter` (name) and `label` (display name) |
| `merge_strategy` | string | No | How to merge results: `side_by_side` (default) or `labeled_concat` |
| `partial_results` | bool | No | Return results even if some target adapters fail (default: `true`) |
| `nl_examples` | list | Yes | Natural language examples for vector matching |
| `timeout_per_adapter` | float | No | Per-adapter timeout override (seconds) |
| `tags` | list | No | Categorization tags |

### Merge Strategies

#### `side_by_side` (default)

Each target adapter's results are returned as separate items in the result list, each annotated with the adapter label in metadata. The LLM presentation layer handles comparison formatting.

Best for: queries where each source returns structurally different data.

#### `labeled_concat`

All result content is concatenated into a single result item with source labels prepended (e.g., `--- Sales Analytics ---\n...`). Metadata includes details from each source.

Best for: queries where sources return similar data and a unified view is preferred.

### Cross-Adapter Configuration

Add to the composite adapter's `config` section:

```yaml
config:
  child_adapters:
    - "intent-sql-sqlite-hr"
    - "intent-sql-postgres"
    - "intent-duckdb-analytics"

  # Cross-adapter template configuration
  cross_adapter_templates:
    enabled: true
    template_library_path:
      - "path/to/cross_adapter_templates.yaml"
    template_collection_name: "composite_cross_adapter_templates"
    store_name: "chroma"

  # Cross-adapter execution settings
  cross_adapter_execution:
    timeout_per_adapter: 10.0       # Timeout per child adapter query (seconds)
    partial_results: true            # Return results even if some adapters fail
    default_merge_strategy: "side_by_side"  # Default merge strategy
```

#### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cross_adapter_templates.enabled` | bool | `false` | Enable cross-adapter template matching |
| `cross_adapter_templates.template_library_path` | list | `[]` | Paths to cross-adapter template YAML files |
| `cross_adapter_templates.template_collection_name` | string | `composite_cross_adapter_templates` | Vector store collection name |
| `cross_adapter_templates.store_name` | string | `chroma` | Vector store type |
| `cross_adapter_execution.timeout_per_adapter` | float | `10.0` | Timeout per adapter in seconds |
| `cross_adapter_execution.partial_results` | bool | `true` | Return partial results on adapter failure |
| `cross_adapter_execution.default_merge_strategy` | string | `side_by_side` | Default merge strategy |

### Cross-Adapter Response Format

```json
{
  "content": "Results from the sales analytics adapter...",
  "metadata": {
    "composite_routing": {
      "cross_adapter": true,
      "template_id": "compare_sales_and_orders",
      "merge_strategy": "side_by_side",
      "similarity_score": 0.87,
      "target_adapters": [
        "intent-duckdb-analytics",
        "intent-sql-postgres"
      ],
      "successful_adapters": [
        "intent-duckdb-analytics",
        "intent-sql-postgres"
      ],
      "failed_adapters": [],
      "total_sources": 2
    },
    "cross_adapter_source": {
      "adapter": "intent-duckdb-analytics",
      "label": "Sales Analytics"
    }
  }
}
```

With `side_by_side`, each result item includes a `cross_adapter_source` field identifying which adapter produced it. With `labeled_concat`, a single result item is returned with all content concatenated and a `source_details` map in metadata.

### Cross-Adapter Routing Metadata Fields

| Field | Description |
|-------|-------------|
| `cross_adapter` | `true` when a cross-adapter template was matched |
| `template_id` | ID of the cross-adapter template |
| `merge_strategy` | Merge strategy used (`side_by_side` or `labeled_concat`) |
| `similarity_score` | Embedding similarity score of the cross-adapter template |
| `target_adapters` | List of child adapter names that were queried |
| `successful_adapters` | Adapters that returned results successfully |
| `failed_adapters` | Adapters that failed (with error details) |
| `total_sources` | Number of adapters that returned results |

### Partial Failure Handling

When `partial_results` is `true` (default), the composite retriever returns results from successful adapters even if some fail. Failed adapters are listed in `failed_adapters` with error details.

When `partial_results` is `false`, any adapter failure causes the entire cross-adapter query to return an error.

### Verbose Logging for Cross-Adapter Queries

With `verbose: true`, cross-adapter routing produces logs like:

```
[Composite] CROSS-ADAPTER query matched template: compare_sales_and_orders
[Composite] Merge strategy: side_by_side
[Composite] Target adapters: ['intent-duckdb-analytics', 'intent-sql-postgres']
[Composite] Successful: ['intent-duckdb-analytics', 'intent-sql-postgres']
[Composite] Score: 0.870
```

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

### Basic Response (Single-Stage)

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

### Multi-Stage Response (Enhanced)

When multi-stage selection is enabled, additional scoring details are included:

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
      "total_matches_found": 7,
      "multistage_scoring": {
        "enabled": true,
        "combined_score": 0.89,
        "embedding_score": 0.92,
        "rerank_score": 0.95,
        "string_similarity_score": 0.78,
        "scoring_details": {
          "embedding_weight": 0.4,
          "rerank_weight": 0.4,
          "string_similarity_weight": 0.2
        }
      }
    }
  },
  "confidence": 0.89
}
```

### Routing Metadata Fields

| Field | Description |
|-------|-------------|
| `selected_adapter` | Name of the child adapter that handled the query |
| `template_id` | ID of the template that was matched and executed |
| `similarity_score` | Embedding similarity score (Stage 1) |
| `adapters_searched` | List of all child adapter names that were searched |
| `total_matches_found` | Total number of template matches across all sources |

### Multi-Stage Scoring Fields (when enabled)

| Field | Description |
|-------|-------------|
| `multistage_scoring.enabled` | Whether multi-stage selection was used |
| `multistage_scoring.combined_score` | Final weighted combined score |
| `multistage_scoring.embedding_score` | Stage 1 embedding similarity |
| `multistage_scoring.rerank_score` | Stage 2 LLM reranker score (null if disabled) |
| `multistage_scoring.string_similarity_score` | Stage 3 string similarity (null if disabled) |
| `multistage_scoring.scoring_details` | Weight configuration used |

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

### 2. Hybrid SQL and API Sources

Combine traditional databases with external APIs:

```yaml
config:
  child_adapters:
    - "intent-sql-postgres-inventory"   # Internal inventory DB
    - "intent-http-pricing-api"         # External pricing API
    - "intent-mongodb-orders"           # Order history
```

### 3. Cross-Source Comparison with Cross-Adapter Templates

Compare data across multiple sources using cross-adapter templates:

```yaml
config:
  child_adapters:
    - "intent-sql-sqlite-hr"        # HR employee data
    - "intent-sql-postgres"         # Customer orders
    - "intent-duckdb-analytics"     # Sales analytics

  cross_adapter_templates:
    enabled: true
    template_library_path:
      - "examples/intent-templates/cross-adapter-template/cross_adapter_templates.yaml"
    template_collection_name: "composite_cross_adapter_templates"
    store_name: "chroma"
```

User queries are routed appropriately:
- "Show me all employees" --> single adapter (HR)
- "What's the revenue trend for Q4?" --> single adapter (Analytics)
- "Compare sales analytics with order data" --> cross-adapter (Analytics + Orders in parallel)
- "Show me data from all sources" --> cross-adapter (HR + Analytics + Orders in parallel)

## Debugging and Testing

### Test Routing Without Execution

The composite retriever provides a `test_routing()` method to debug routing decisions without actually executing queries. When multi-stage selection is enabled, it shows all score types:

```python
# Available via the adapter's test_routing method
result = await composite_adapter.test_routing("Show me all Tesla vehicles")

# Returns (with multi-stage enabled):
{
  "query": "Show me all Tesla vehicles",
  "total_matches": 5,
  "matches_above_threshold": 3,
  "all_matches": [
    {
      "template_id": "ev_count_by_make",
      "source_adapter": "intent-duckdb-ev-population",
      "embedding_score": 0.92,
      "combined_score": 0.89,
      "rerank_score": 0.95,
      "string_similarity_score": 0.78,
      "description": "Count electric vehicles by make",
      "nl_examples": ["How many Teslas are there?", "Count vehicles by make"],
      "above_threshold": true,
      "scoring_details": {
        "embedding_weight": 0.4,
        "rerank_weight": 0.4,
        "string_similarity_weight": 0.2
      }
    },
    ...
  ],
  "routing_decision": {
    "would_route_to": "intent-duckdb-ev-population",
    "selected_template": "ev_count_by_make",
    "selection_score": 0.89,
    "embedding_score": 0.92,
    "rerank_score": 0.95,
    "string_similarity_score": 0.78,
    "reason": "highest_combined_score_above_threshold"
  },
  "configuration": {
    "confidence_threshold": 0.4,
    "adapters_searched": ["intent-sql-sqlite-hr", "intent-duckdb-ev-population"],
    "multistage_enabled": true,
    "reranking_enabled": true,
    "string_similarity_enabled": true,
    "scoring_weights": {
      "embedding": 0.4,
      "reranking": 0.4,
      "string_similarity": 0.2
    }
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
  },
  "multistage_selection": {
    "enabled": true,
    "reranking": {
      "enabled": true,
      "provider": "anthropic",
      "top_candidates": 10,
      "weight": 0.4
    },
    "string_similarity": {
      "enabled": true,
      "algorithm": "jaro_winkler",
      "weight": 0.2,
      "compare_fields": ["description", "nl_examples"]
    },
    "scoring": {
      "embedding_weight": 0.4,
      "normalize_scores": true,
      "tie_breaker": "embedding"
    }
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
[Composite] Total matches: 5
[Composite] Combined Score: 0.890
[Composite]   - Embedding: 0.920
[Composite]   - Rerank: 0.950
[Composite]   - String Similarity: 0.780
```

When multi-stage is disabled, only the embedding score is shown:

```
[Composite] Routed to: intent-duckdb-ev-population
[Composite] Template: ev_count_by_make
[Composite] Score: 0.920
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

The composite retriever over-fetches `max_templates_per_source × 3` vectors from each child to account for per-example deduplication, then trims to `max_templates_per_source` unique templates per source. This keeps memory usage bounded even with many child adapters:

```
Vectors fetched per source = max_templates_per_source × 3
Unique templates per source = max_templates_per_source (after dedup)
Total unique templates = num_child_adapters × max_templates_per_source
```

## Limitations

1. **Single Source Execution (default)**: Without cross-adapter templates, only the best-matching source executes the query. Enable cross-adapter templates for multi-source queries.

2. **Shared Embedding Requirement**: All child adapters should ideally use the same embedding model, or the similarity scores may not be directly comparable.

3. **Child Adapter Initialization**: Child adapters must be fully initialized before the composite retriever can use them. The composite does not initialize child adapters.

4. **No Cross-Source Joins**: The composite retriever cannot join data across sources at the SQL level. Cross-adapter templates execute independent queries per source and merge the results, but do not perform relational joins across databases.

5. **Cross-Adapter Template Authoring**: Cross-adapter templates must be authored manually, specifying which target adapters to query. There is no automatic detection of multi-source queries without a matching cross-adapter template.

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
| `server/retrievers/base/intent_composite_base.py` | Base class with core routing logic, multi-stage scoring, and cross-adapter template support |
| `server/retrievers/implementations/composite/composite_intent_retriever.py` | Full implementation with debug methods |
| `server/utils/string_similarity.py` | String similarity utilities (Jaro-Winkler, Levenshtein) |
| `config/adapters/composite.yaml` | Example adapter configurations (including cross-adapter template config) |
| `config/config.yaml` (composite_retrieval section) | Global multi-stage selection settings |
| `examples/intent-templates/cross-adapter-template/` | Example cross-adapter template definitions |

### Data Structures

```python
@dataclass
class TemplateMatch:
    """Represents a template match from a child adapter."""
    template_id: str          # Unique template identifier
    source_adapter: str       # Name of the child adapter
    similarity_score: float   # Embedding similarity score (Stage 1)
    template_data: Dict       # Full template definition
    embedding_text: str       # Text used for embedding

    # Multi-stage scoring fields (populated when enabled)
    rerank_score: Optional[float] = None           # Stage 2: LLM reranker score
    string_similarity_score: Optional[float] = None # Stage 3: String similarity
    combined_score: Optional[float] = None         # Weighted combined score

    # Scoring metadata for debugging
    scoring_details: Dict[str, Any] = field(default_factory=dict)
```

### String Similarity Utilities

The `StringSimilarity` class in `server/utils/string_similarity.py` provides:

```python
from utils.string_similarity import StringSimilarity

# Single comparison
score = StringSimilarity.jaro_winkler_similarity("hello", "hallo")  # 0.88

# Best match from text (checks full text and individual words)
score = StringSimilarity.calculate_best_text_similarity(
    query="show employees",
    text="Show all employees in department",
    algorithm="jaro_winkler"
)

# Find best match from list
result = StringSimilarity.find_best_match(
    query="show employees",
    candidates=["Show customers", "Show employees", "List orders"],
    algorithm="jaro_winkler",
    min_threshold=0.5
)
```

Supported algorithms:
- `jaro_winkler`: Best for short strings and prefix matching (recommended)
- `levenshtein`: Edit distance, good for typo tolerance
- `ratio`: Simple character ratio (fastest)

## Related Documentation

- [Adapters Overview](./adapters.md) - General adapter architecture
- [Adapter Configuration](./adapter-configuration.md) - Configuration management
- [Intent-SQL RAG System](../intent-sql-rag-system.md) - Intent adapter internals

