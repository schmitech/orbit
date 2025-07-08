# SQL Adapter Implementation

## Overview

The SQL adapter has been implemented for SQL retrievers in the Orbit system, providing enhanced validation, performance safeguards, and query monitoring according to the principles outlined in the [adapter granularity strategy document](roadmap/adapters/adapter-granularity-strategy.md).

## Implementation Details

### 1. Enhanced SQL Adapter Validation Service

**File**: `server/services/sql_adapter_validation_service.py`

The SQL adapter validation service provides:
- **SQL Adapter Detection**: Identifies SQL vs non-SQL adapters automatically
- **SQL Complexity Detection**: Categorizes SQL adapters as single-table, materialized view, or multi-table
- **SQL Query Risk Analysis**: Analyzes SQL queries for performance and security risks (JOINs, subqueries, etc.)
- **Resource Limit Validation**: Enforces limits based on SQL adapter complexity
- **SQL Security Validation**: Ensures proper SQL security filters, parameterization, and column access

### 2. Enhanced SQL Retriever Base Class

**File**: `server/retrievers/base/sql_retriever.py`

Enhancements include:
- **Query Monitoring**: Tracks query execution time and result set sizes
- **Security Filters**: Automatically applies security filters to queries
- **Column Restrictions**: Limits which columns can be accessed
- **Performance Safeguards**: Enforces timeouts and result limits

### 3. Configuration Schema Updates

**File**: `config.yaml`

Added configurations for:
- **Adapter Limits**: Resource limits by complexity level
- **Example Configurations**: Demonstrations of different adapter patterns
- **Monitoring Settings**: Query monitoring and validation controls

### 4. SQL Adapter Validation Tests

**File**: `server/tests/test_adapter_validation.py`

A comprehensive pytest test suite for SQL adapters:
- Validating SQL adapter configurations against granularity strategy
- Testing SQL query risk analysis and security validation
- Verifying SQL-specific resource limit enforcement
- Integration testing with actual config.yaml SQL adapters

## How to Use

### SQL Adapter Configuration

Here's how to configure different types of SQL adapters:

#### Single-Table Adapter (Recommended)
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

#### Materialized View Adapter
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

#### Multi-Table Adapter (Requires Approval)
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

#### Performance Settings
- `max_results`: Maximum number of results to return
- `query_timeout`: Maximum query execution time in milliseconds
- `enable_query_monitoring`: Enable performance and security monitoring

#### Security Settings
- `security_filter`: SQL condition automatically added to all queries
- `allowed_columns`: List of columns that can be accessed
- `required_parameters`: Parameters that must be provided for multi-table queries

#### Approval Settings
- `approved_by_admin`: Required for high-risk or multi-table adapters

### Resource Limits

The system enforces different limits based on adapter complexity:

```yaml
adapter_limits:
  single_table:
    max_results: 500
    query_timeout: 5000
    memory_limit: "100MB"
    
  materialized_view:
    max_results: 1000
    query_timeout: 10000
    memory_limit: "200MB"
    
  multi_table:
    max_results: 100
    query_timeout: 15000
    memory_limit: "50MB"
    required_approval: true
```

### Validation and Monitoring

#### Running Validation Tests
```bash
# Run all adapter validation tests
python -m pytest server/tests/test_adapter_validation.py -v

# Run tests against current config.yaml
python -m pytest server/tests/test_adapter_validation.py::test_validation_script_functionality -v

# Run only security-related tests
python -m pytest server/tests/test_adapter_validation.py -k "security" -v

# Run tests with detailed output
python -m pytest server/tests/test_adapter_validation.py -v -s
```

#### Query Monitoring
When `enable_query_monitoring` is true, the system will:
- Log slow queries (>5 seconds)
- Log large result sets (>1000 rows)
- Track query execution statistics
- Validate query patterns for security risks

#### Risk Levels
- **LOW**: Simple queries with proper filters and limits
- **MEDIUM**: Queries with some complexity but within safety bounds
- **HIGH**: Complex queries requiring manual review and approval

#### Test Categories

The validation test suite includes several categories:

1. **Unit Tests**: Test individual validation components
   - Service initialization
   - SQL adapter detection
   - Complexity determination
   - Query risk analysis

2. **Integration Tests**: Test with actual configuration
   - Current config.yaml validation
   - SQL vs non-SQL adapter handling
   - Resource limit enforcement

3. **Security Tests**: Focus on security validation
   - Dangerous query pattern detection
   - Security filter validation
   - Parameter requirement checking

4. **Performance Tests**: Validate performance safeguards
   - Query optimization suggestions
   - Resource limit validation
   - Timeout enforcement

## Best Practices

### ✅ Recommended Patterns

1. **Single-Table Adapters**: Use for most scenarios
   - Predictable performance
   - Simple to secure
   - Easy to monitor

2. **Materialized Views**: Use for complex aggregations
   - Pre-computed results
   - Better performance than JOINs
   - Controlled refresh schedules

3. **Security-First Configuration**:
   - Always include `security_filter`
   - Specify `allowed_columns` where possible
   - Use parameterized queries

### ❌ Patterns to Avoid

1. **Open-ended JOINs**: Without proper filters
2. **Missing LIMIT clauses**: Can cause performance issues
3. **SELECT * queries**: Inefficient and insecure
4. **Unparameterized multi-table queries**: Security risk

## Migration Guide

### For Existing Adapters

1. **Add Required Fields**:
   ```yaml
   config:
     query_timeout: 5000
     enable_query_monitoring: true
   ```

2. **Add Security Measures**:
   ```yaml
   config:
     security_filter: "active = true"
     allowed_columns: ["id", "name", "email"]
   ```

3. **Validate Configuration**:
   ```bash
   python -m pytest server/tests/test_adapter_validation.py -v
   ```

### For New Adapters

1. Start with single-table adapters
2. Use the validation script during development
3. Follow the configuration examples
4. Test with query monitoring enabled

## Error Handling

The system provides detailed error messages for:
- **Configuration Errors**: Missing required fields
- **Performance Issues**: Queries exceeding limits
- **Security Violations**: Unsafe query patterns
- **Approval Requirements**: Multi-table queries without approval

## Performance Impact

The implementation adds minimal overhead:
- Validation occurs at startup
- Query monitoring adds <1ms per query
- Security filters are applied at SQL level
- Memory usage is bounded by configuration limits

## Future Enhancements

Planned improvements include:
- Automatic query optimization suggestions
- Machine learning-based risk assessment
- Dynamic resource allocation based on usage
- Integration with database query planners

## Troubleshooting

### Common Issues

1. **Validation Errors**:
   - Check required fields are present
   - Ensure limits are within bounds
   - Verify security filters are valid SQL

2. **Performance Warnings**:
   - Review query patterns
   - Check for missing indexes
   - Consider using materialized views

3. **Security Violations**:
   - Add parameterized WHERE clauses
   - Include security filters
   - Limit column access

### Getting Help

- Run the validation tests for detailed error messages
- Review the adapter granularity strategy document
- Enable verbose logging for detailed information
- Check the test fixtures for example configurations
- Use `pytest -v -s` for detailed test output 