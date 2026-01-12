# DuckDB-Specific Guide for Intent Adapters

This guide covers DuckDB-specific features and considerations when creating intent adapters for DuckDB databases.

## DuckDB Overview

DuckDB is an in-process analytical database optimized for analytical workloads. Key characteristics:

- **Columnar Storage**: Optimized for analytical queries with columnar storage
- **In-Process**: Embedded database (no separate server process)
- **File-Based or In-Memory**: Supports both persistent file-based databases and in-memory databases
- **SQL Compatibility**: PostgreSQL-like SQL syntax with additional analytical functions
- **Performance**: Vectorized execution engine optimized for analytical workloads

## Connection Configuration

### File-Based Database

```yaml
duckdb:
  database: "./data/analytics.duckdb"
  read_only: false
  access_mode: "automatic"
```

### In-Memory Database

```yaml
duckdb:
  database: ":memory:"
  read_only: false
```

### Read-Only Access

```yaml
duckdb:
  database: "./data/readonly.duckdb"
  read_only: true
  access_mode: "read_only"
```

## SQL Syntax Considerations

### Parameter Binding

DuckDB supports both named and positional parameters:

**Named Parameters** (recommended):
```sql
SELECT * FROM sales WHERE region = :region AND year = :year
```

**Positional Parameters**:
```sql
SELECT * FROM sales WHERE region = ? AND year = ?
```

**Note**: The intent retriever automatically converts PostgreSQL-style parameters (`%(name)s`) to DuckDB format (`:name`).

### Direct File Querying

One of DuckDB's unique features is the ability to query files directly:

```sql
-- Query CSV file
SELECT * FROM read_csv_auto('sales.csv') WHERE region = :region

-- Query Parquet file
SELECT * FROM read_parquet('sales.parquet') WHERE year = :year

-- Query multiple files
SELECT * FROM read_csv_auto(['file1.csv', 'file2.csv'])
```

Templates can leverage this for dynamic data loading:

```yaml
- id: query_csv_sales
  sql: SELECT * FROM read_csv_auto(:file_path) WHERE date >= :start_date
  parameters:
    - name: file_path
      type: string
      description: Path to CSV file
    - name: start_date
      type: date
      description: Start date filter
```

### Analytical Functions

DuckDB supports advanced analytical SQL functions:

**Window Functions**:
```sql
SELECT 
  product,
  sales,
  RANK() OVER (PARTITION BY category ORDER BY sales DESC) as rank
FROM products
```

**Grouping Sets**:
```sql
SELECT region, category, SUM(sales) 
FROM sales 
GROUP BY GROUPING SETS ((region), (category), ())
```

**Time-Series Functions**:
```sql
SELECT 
  date_trunc('month', date) as month,
  SUM(sales) as monthly_sales
FROM sales
GROUP BY month
```

## Template Generation

Templates follow the same structure as SQL intent templates but can leverage DuckDB-specific features:

### Example Template Structure

```yaml
- id: find_top_products
  description: Find top N products by sales in a region
  sql: |
    SELECT 
      product_id,
      product_name,
      SUM(sales_amount) as total_sales
    FROM sales
    WHERE region = :region
    GROUP BY product_id, product_name
    ORDER BY total_sales DESC
    LIMIT :limit
  parameters:
    - name: region
      type: string
      required: true
    - name: limit
      type: integer
      required: false
      default: 10
  nl_examples:
    - Show me top products in the west region
    - What are the best selling products in California?
    - List top 5 products by sales in the west
```

## Performance Best Practices

### 1. Use Columnar-Friendly Patterns

DuckDB is optimized for columnar operations:

```sql
-- Good: Filter early
SELECT * FROM sales WHERE date >= :start_date AND region = :region

-- Less efficient: Filter after aggregation
SELECT * FROM (SELECT * FROM sales GROUP BY region) WHERE region = :region
```

### 2. Leverage Vectorization

DuckDB's vectorized execution works best with:

- Large batch operations
- Columnar data access patterns
- Analytical aggregations

### 3. File Query Optimization

When querying files directly:

```sql
-- Efficient: Use projection
SELECT product, sales FROM read_csv_auto('sales.csv') WHERE region = :region

-- Less efficient: Select all then filter
SELECT * FROM read_csv_auto('sales.csv') WHERE region = :region
```

### 4. In-Memory vs. File-Based

- **In-Memory** (`:memory:`): Best for temporary data, fast queries, no persistence
- **File-Based**: Best for persistent data, larger datasets, shared access

## Domain Configuration

Domain configurations work the same as SQL intent templates. Example:

```yaml
domain_name: Analytics Database
description: Sales and product analytics
domain_type: analytical
entities:
  sales:
    name: sales
    entity_type: primary
    table_name: sales
    primary_key: id
    searchable_fields:
      - product_name
      - region
      - category
fields:
  sales:
    product_id:
      name: product_id
      data_type: integer
      db_column: product_id
    sales_amount:
      name: sales_amount
      data_type: decimal
      db_column: sales_amount
```

## Common Patterns

### Time-Series Analysis

```sql
SELECT 
  date_trunc('month', sale_date) as month,
  region,
  SUM(amount) as monthly_total
FROM sales
WHERE sale_date >= :start_date
GROUP BY month, region
ORDER BY month, region
```

### Top-N Queries

```sql
SELECT 
  product_name,
  SUM(sales_amount) as total
FROM sales
WHERE category = :category
GROUP BY product_name
ORDER BY total DESC
LIMIT :n
```

### Comparative Analysis

```sql
SELECT 
  region,
  SUM(CASE WHEN year = :year1 THEN sales_amount ELSE 0 END) as year1_sales,
  SUM(CASE WHEN year = :year2 THEN sales_amount ELSE 0 END) as year2_sales,
  SUM(CASE WHEN year = :year2 THEN sales_amount ELSE 0 END) - 
  SUM(CASE WHEN year = :year1 THEN sales_amount ELSE 0 END) as difference
FROM sales
GROUP BY region
```

## Troubleshooting

### Connection Issues

- **Error**: "database file not found"
  - Solution: Ensure the database path is correct and accessible
  - Check file permissions if using file-based database

- **Error**: "database is locked"
  - Solution: Ensure only one process is writing to the database
  - Use read-only mode for concurrent read access

### Query Execution Issues

- **Error**: "parameter binding failed"
  - Solution: Ensure parameter names match between template and query
  - Check that parameters are provided in the correct format

- **Error**: "function not found"
  - Solution: Verify the function is available in DuckDB
  - Check DuckDB version compatibility

### Performance Issues

- **Slow queries**: Consider using file-based database instead of in-memory for large datasets
- **Memory issues**: Use read-only mode or limit result sets
- **File queries**: Prefer Parquet format over CSV for better performance

## Migration from SQLite/PostgreSQL

If you have existing SQL intent templates for SQLite or PostgreSQL:

1. **Parameter Format**: Convert `%(name)s` to `:name` (automatic in retriever)
2. **SQL Syntax**: Most PostgreSQL syntax works directly in DuckDB
3. **File Queries**: Consider adding templates that query files directly
4. **Performance**: DuckDB may require different query patterns for optimal performance

## See Also

- [DuckDB SQL Documentation](https://duckdb.org/docs/sql/introduction)
- [DuckDB Functions](https://duckdb.org/docs/sql/functions/overview)
- [SQL Intent Template Generator](../sql-intent-template/README.md)

