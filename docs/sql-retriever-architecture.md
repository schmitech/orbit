# SQL Retriever Architecture & Implementation Guide

This guide provides a comprehensive overview of the SQL retriever architecture in ORBIT, covering its design, implementation, configuration, and best practices. The architecture is designed to be **database-agnostic**, supporting any SQL database through a common interface while allowing for database-specific optimizations.

## Architecture Hierarchy

The SQL retriever architecture is a specialization of the base retriever system.

```
BaseRetriever (abstract base for all retrievers)
└── AbstractSQLRetriever (database-agnostic SQL functionality)
    ├── relational/
    │   ├── SQLiteRetriever (SQLite-specific implementation)
    │   ├── PostgreSQLRetriever (PostgreSQL-specific implementation)
    │   └── MySQLRetriever (MySQL-specific implementation)
    └── qa/
        └── QASSQLRetriever (QA domain specialization of SQLite)
```

### Separation of Concerns

-   **Common Logic**: `AbstractSQLRetriever` handles database-agnostic functionality like text tokenization, similarity scoring, and domain adapter integration.
-   **Database Logic**: Concrete implementations like `SQLiteRetriever` or `PostgreSQLRetriever` handle the specifics of database connections, query execution, and schema verification.
-   **Domain Logic**: Specialized retrievers like `QASSQLRetriever` extend a database implementation to add domain-specific logic (e.g., prioritizing QA fields).

## Supported Databases

| Database | Implementation | Status | Special Features | Domain Specializations |
|:---|:---|:---|:---|:---|
| **SQLite** | `relational.SQLiteRetriever` | ✅ Complete | File-based, FTS5 support | `qa.QASSQLRetriever` (Q&A) |
| **PostgreSQL** | `relational.PostgreSQLRetriever` | ✅ Complete | Full-text search, JSON ops | *Easy to add* |
| **MySQL** | `relational.MySQLRetriever` | ✅ Complete | FULLTEXT indexes, optimized LIKE | *Easy to add* |

## Configuration

SQL adapters are configured in `config/adapters.yaml`. The configuration allows for fine-grained control over performance and security.

### SQL Adapter Configuration Patterns

#### 1. Single-Table Adapter (Recommended)
This is the safest and most common pattern. The retriever queries a single, well-indexed table.

```yaml
- name: "customer-profiles"
  type: "retriever"
  datasource: "postgres"
  adapter: "sql"
  implementation: "retrievers.implementations.relational.PostgreSQLRetriever"
  config:
    table: "customers"
    max_results: 100
    query_timeout: 3000
    allowed_columns: ["id", "name", "email", "department"]
    security_filter: "active = true"
    enable_query_monitoring: true
```

#### 2. Materialized View Adapter
For complex queries or aggregations, it is best practice to pre-compute the results in a materialized view and have the adapter query that view. This provides excellent performance and security.

```yaml
- name: "customer-order-summary"
  type: "retriever"
  datasource: "postgres"
  adapter: "sql"
  implementation: "retrievers.implementations.relational.PostgreSQLRetriever"
  config:
    table: "customer_order_summary_mv"
    max_results: 200
    query_timeout: 10000
    cache_ttl: 3600
    enable_query_monitoring: true
```

#### 3. Multi-Table Adapter (Requires Approval)
For cases where a JOIN is unavoidable, you can use a query template. This pattern is considered high-risk and requires administrative approval in the configuration.

```yaml
- name: "recent-customer-activity"
  type: "retriever"
  datasource: "postgres"
  adapter: "sql"
  implementation: "retrievers.implementations.relational.PostgreSQLRetriever"
  config:
    query_template: |
      SELECT c.name, o.order_date, o.total
      FROM customers c
      INNER JOIN orders o ON c.id = o.customer_id
      WHERE o.created_at >= NOW() - INTERVAL '7 days'
      AND c.id = {customer_id}
      ORDER BY o.created_at DESC
      LIMIT 20
    max_results: 20
    query_timeout: 15000
    required_parameters: ["customer_id"]
    approved_by_admin: true
    enable_query_monitoring: true
```

### Configuration Options

-   `max_results`: Maximum number of results to return.
-   `query_timeout`: Maximum query execution time in milliseconds.
-   `enable_query_monitoring`: Enable performance and security monitoring.
-   `security_filter`: SQL condition automatically added to all queries (e.g., `active = true`).
-   `allowed_columns`: List of columns that can be accessed.
-   `required_parameters`: For multi-table queries, parameters that must be provided.
-   `approved_by_admin`: Must be `true` for high-risk or multi-table adapters.

## Best Practices

#### ✅ Recommended Patterns

1.  **Single-Table Adapters**: Use for most scenarios for predictable performance and security.
2.  **Materialized Views**: Use for complex aggregations to ensure high performance.
3.  **Security-First Configuration**: Always include a `security_filter` and specify `allowed_columns`.

#### ❌ Patterns to Avoid

1.  **Open-ended JOINs**: Avoid complex joins in adapters; use a materialized view instead.
2.  **Missing LIMIT clauses**: Can cause performance issues.
3.  **`SELECT *` queries**: Inefficient and insecure; specify columns with `allowed_columns`.

## New Base Class Features

The `BaseSQLDatabaseRetriever` provides several modern features out-of-the-box for all SQL implementations.

-   **Environment Variable Support**: Use `${VAR_NAME}` or `${VAR_NAME:default_value}` in your configuration for sensitive data like passwords.
-   **Connection Management**: Built-in support for connection pooling and automatic retries on transient connection failures.
-   **Automatic Type Conversion**: Converts common database types (Decimal, datetime, UUID, etc.) to standard Python types.
-   **Query Monitoring**: Automatically logs slow queries and queries that return large result sets.

## Extending the Architecture

### Creating New Database Support

1.  **Inherit from `BaseSQLDatabaseRetriever`**: This new base class provides most of the common functionality.
2.  **Implement Required Methods**: You only need to implement a few methods specific to your database:
    -   `_get_datasource_name()`: Return the name for the config (e.g., `'oracle'`).
    -   `create_connection()`: Code to connect to the database.
    -   `_execute_raw_query()`: Code to execute a query and return results.
    -   `_close_connection()`: Code to close the connection.
3.  **Add Optimizations (Optional)**: Override `_get_search_query` to add database-specific search features like Oracle's text indexing.
4.  **Register with Factory**: Add `RetrieverFactory.register_retriever('your_db', YourRetrieverClass)` to the bottom of your file.

### Creating New Domain Specializations

1.  **Extend a Database Implementation**: Inherit from an existing concrete retriever like `PostgreSQLRetriever`.
2.  **Add Domain-Specific Logic**: Override methods like `_get_search_query` to add logic specific to your domain (e.g., prioritizing searches on a `question` column for a QA system).

This architecture makes it simple to add support for new databases and to create specialized retrievers for different business domains with minimal code duplication.
