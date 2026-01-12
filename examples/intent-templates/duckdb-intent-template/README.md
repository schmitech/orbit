# DuckDB Intent Template Generator

This tool generates SQL templates for DuckDB intent adapters, enabling natural language queries against DuckDB databases. DuckDB is an in-process analytical database optimized for analytical queries, making it ideal for data analytics, reporting, and business intelligence use cases.

## Overview

DuckDB Intent Template Generator works similarly to the SQL Intent Template Generator but is optimized for DuckDB's specific features:

- **Columnar Storage**: Optimized for analytical workloads with columnar storage
- **SQL Compatibility**: PostgreSQL-like SQL syntax with advanced analytical functions
- **File Querying**: Can directly query CSV, Parquet, and other file formats
- **Performance**: High-performance analytical queries with vectorized execution
- **In-Memory or File-Based**: Supports both in-memory (`:memory:`) and file-based databases

## Quick Start

### 1. Create a DuckDB Database

First, create or populate your DuckDB database. You can use the example data generation script:

```bash
cd examples/analytics
python generate_analytics_data.py --records 1000 --output analytics.duckdb
```

### 2. Generate Templates

Use the SQL Intent Template Generator (shared with SQL templates) to generate templates:

```bash
cd ../..
python template_generator.py \
    --schema examples/analytics/analytics.sql \
    --queries examples/analytics/analytics_test_queries.md \
    --output analytics-templates.yaml \
    --config configs/analytics-config.yaml
```

### 3. Configure the Adapter

Add the DuckDB intent adapter to `config/adapters.yaml`:

```yaml
- name: "intent-duckdb-analytics"
  enabled: true
  type: "retriever"
  datasource: "duckdb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentDuckDBRetriever"
  inference_provider: "ollama_cloud"
  model: "gpt-oss:20b-cloud"
  embedding_provider: "openai"
  config:
    domain_config_path: "utils/duckdb-intent-template/examples/analytics/analytics_domain.yaml"
    template_library_path:
      - "utils/duckdb-intent-template/examples/analytics/analytics_templates.yaml"
    template_collection_name: "duckdb_analytics_templates"
    store_name: "chroma"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 100
    reload_templates_on_start: true
    force_reload_templates: true
```

## DuckDB-Specific Features

### Parameter Binding

DuckDB supports both named parameters (`:name`) and positional parameters (`?`). The intent retriever automatically converts PostgreSQL-style parameters (`%(name)s`) to DuckDB format.

### Direct File Querying

DuckDB can query CSV and Parquet files directly. Templates can include queries like:

```sql
SELECT * FROM read_csv_auto('sales_data.csv') WHERE region = :region
```

### Analytical Functions

DuckDB supports advanced analytical functions that are ideal for business intelligence queries:

- Window functions (`ROW_NUMBER()`, `RANK()`, etc.)
- Aggregations with grouping sets
- Pivot/unpivot operations
- Time-series functions

## Examples

See the `examples/analytics/` directory for a complete example including:

- Database schema (`analytics.sql`)
- Domain configuration (`analytics_domain.yaml`)
- Template library (`analytics_templates.yaml`)
- Test queries (`analytics_test_queries.md`)
- Data generation script (`generate_analytics_data.py`)

## Differences from SQLite/PostgreSQL

1. **Connection**: Uses `duckdb.connect()` instead of database-specific connections
2. **File Support**: Can directly query CSV/Parquet files without importing
3. **Performance**: Optimized for analytical queries, not transactional workloads
4. **SQL Extensions**: Supports additional analytical SQL functions

## Configuration

### Datasource Configuration

In `config/datasources.yaml`:

```yaml
duckdb:
  database: ":memory:"  # or path to .duckdb file
  read_only: false
  access_mode: "automatic"
  threads: null
```

### Adapter Configuration

The DuckDB intent adapter supports all standard intent adapter configuration options, plus DuckDB-specific settings:

- `database`: Database path (defaults to `:memory:`)
- `read_only`: Read-only mode (default: `false`)
- `access_mode`: Access mode (`automatic`, `read_only`, `read_write`)
- `threads`: Number of threads for parallel execution

## Troubleshooting

### Connection Issues

- Ensure `duckdb` Python package is installed: `pip install duckdb`
- Check that the database path is accessible
- For file-based databases, ensure write permissions if `read_only: false`

### Parameter Binding Issues

DuckDB uses standard parameterized queries. The retriever automatically converts PostgreSQL-style parameters (`%(name)s`) to DuckDB format (`:name`).

### Performance Tips

- Use columnar-friendly query patterns (filter early, aggregate efficiently)
- Leverage DuckDB's analytical functions for complex queries
- Consider using in-memory database for temporary data or file queries for persistent data

## See Also

- [SQL Intent Template Generator](../sql-intent-template/README.md) - Shared template generation tools
- [DuckDB Documentation](https://duckdb.org/docs/) - Official DuckDB documentation
- [Intent SQL RAG System](../../../docs/intent-sql-rag-system.md) - Intent adapter architecture

