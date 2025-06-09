# Adapter Granularity Strategy: Single-Table vs Multi-Table Design

## Overview

This document analyzes the optimal granularity for adapter design, weighing the benefits of single-table adapters against more complex multi-table configurations, with focus on performance, security, and organizational best practices.

## The Case for Single-Table Adapters

### 🎯 **Primary Benefits**

#### 1. **Performance Predictability**
```yaml
# Single table adapter - predictable performance
- name: "customer-support-tickets"
  datasource: "postgres"
  config:
    table: "support_tickets"
    max_results: 50
    query_timeout: 5000ms  # Predictable limits
```

#### 2. **Resource Control**
- **Memory Usage**: Bounded by single table size
- **Query Complexity**: No unexpected JOIN operations
- **Index Optimization**: Focus on single table indexes
- **Caching Strategy**: Simple table-level caching

#### 3. **Security Isolation**
```yaml
# Clear permission boundaries
- name: "hr-employee-data"
  config:
    table: "employees"
    security_filter: "department_id = {user.department}"
    allowed_columns: ["name", "email", "department"]  # No sensitive data
```

## Problems with Multi-Table Adapters

### ⚠️ **Performance Risks**

#### 1. **Expensive JOIN Operations**
```sql
-- Dangerous: Could scan millions of records
SELECT * FROM orders o
JOIN customers c ON o.customer_id = c.id
JOIN products p ON o.product_id = p.id
JOIN reviews r ON p.id = r.product_id
WHERE o.created_at > '2020-01-01'
```

#### 2. **Cartesian Product Risk**
```sql
-- Accidental cartesian product
SELECT * FROM users u, orders o, products p
-- Missing JOIN conditions = server killer
```

#### 3. **Resource Exhaustion**
- **Memory Bloat**: Large result sets from JOINs
- **CPU Spikes**: Complex query planning
- **I/O Saturation**: Reading multiple large tables
- **Lock Contention**: Holding locks across tables

## Recommended Adapter Design Patterns

### Pattern 1: Single-Entity Adapters

```yaml
adapters:
  # Customer data only
  - name: "customer-profiles"
    datasource: "postgres"
    config:
      table: "customers"
      max_results: 100
      query_timeout: 3000
      allowed_operations: ["select"]
      
  # Order data only  
  - name: "customer-orders"
    datasource: "postgres"
    config:
      table: "orders"
      max_results: 50
      query_timeout: 2000
      security_filter: "customer_id = {user.customer_id}"
      
  # Product catalog only
  - name: "product-catalog"
    datasource: "postgres"
    config:
      table: "products"
      max_results: 200
      query_timeout: 1000
      cache_ttl: 3600  # Products change less frequently
```

### Pattern 2: Denormalized View Adapters

```yaml
# Pre-computed materialized views for complex data
adapters:
  - name: "customer-order-summary"
    datasource: "postgres"
    config:
      # Use materialized view instead of JOINs
      table: "customer_order_summary_mv"
      max_results: 100
      refresh_schedule: "daily"
      # View contains: customer_name, total_orders, last_order_date, etc.
```

### Pattern 3: Controlled Multi-Table (When Necessary)

```yaml
# Only for specific, well-optimized scenarios
adapters:
  - name: "recent-customer-activity"
    datasource: "postgres"
    config:
      # Carefully crafted query with limits
      query_template: |
        SELECT c.name, o.order_date, o.total
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '7 days'
        AND c.id = {customer_id}  -- Always filter by specific customer
        ORDER BY o.created_at DESC
        LIMIT 20
      max_results: 20  # Hard limit
      query_timeout: 2000
      required_parameters: ["customer_id"]  # Prevent full table scans
```

## Implementation Strategy

### 1. **Adapter Validation Rules**

```python
# server/services/adapter_service.py - Enhanced validation

class AdapterService:
    async def validate_adapter_config(self, adapter_config: Dict[str, Any]) -> List[str]:
        """Enhanced validation with performance safeguards"""
        errors = []
        config = adapter_config.get('config', {})
        
        # Check for performance safeguards
        if not config.get('max_results'):
            errors.append("max_results is required to prevent runaway queries")
        elif config.get('max_results') > 1000:
            errors.append("max_results cannot exceed 1000 for performance")
            
        if not config.get('query_timeout'):
            errors.append("query_timeout is required to prevent long-running queries")
        elif config.get('query_timeout') > 30000:  # 30 seconds
            errors.append("query_timeout cannot exceed 30 seconds")
            
        # Check for dangerous patterns
        query_template = config.get('query_template', '')
        if 'JOIN' in query_template.upper():
            if not config.get('required_parameters'):
                errors.append("JOIN queries must have required_parameters to prevent full table scans")
                
        # Validate single table access
        if config.get('table') and config.get('query_template'):
            errors.append("Use either 'table' (simple) or 'query_template' (complex), not both")
            
        return errors
```

### 2. **Resource Limits per Adapter Type**

```yaml
# config.yaml - Resource limits by adapter complexity
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
    max_results: 100  # Lower limit for complex queries
    query_timeout: 15000
    memory_limit: "50MB"
    required_approval: true  # Require admin approval
```

### 3. **Query Pattern Detection**

```python
class QueryAnalyzer:
    """Analyze queries for performance risks"""
    
    def analyze_query_risk(self, query: str) -> Dict[str, Any]:
        """Analyze query for potential performance issues"""
        risk_score = 0
        warnings = []
        
        query_upper = query.upper()
        
        # Check for JOINs
        join_count = query_upper.count('JOIN')
        if join_count > 0:
            risk_score += join_count * 10
            warnings.append(f"Query contains {join_count} JOIN operations")
            
        # Check for subqueries
        if 'SELECT' in query_upper[query_upper.find('SELECT') + 6:]:
            risk_score += 15
            warnings.append("Query contains subqueries")
            
        # Check for WHERE clause
        if 'WHERE' not in query_upper:
            risk_score += 25
            warnings.append("Query lacks WHERE clause - potential full table scan")
            
        # Check for LIMIT
        if 'LIMIT' not in query_upper:
            risk_score += 20
            warnings.append("Query lacks LIMIT clause")
            
        risk_level = "LOW" if risk_score < 20 else "MEDIUM" if risk_score < 50 else "HIGH"
        
        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "warnings": warnings,
            "approved": risk_score < 50  # Auto-approve only low/medium risk
        }
```

## Organizational Benefits of Single-Table Design

### 1. **Clear Data Ownership**
```yaml
# Each department owns specific tables/adapters
departments:
  legal:
    adapters: ["legal-cases", "legal-documents", "legal-contracts"]
    tables: ["cases", "documents", "contracts"]
    
  finance:
    adapters: ["financial-reports", "budget-data", "expense-tracking"]  
    tables: ["reports", "budgets", "expenses"]
```

### 2. **Simplified Permissions**
```python
# Simple table-level permissions
permissions = {
    "legal-cases": ["legal_team", "compliance_team"],
    "financial-reports": ["finance_team", "executives"],
    "customer-data": ["sales_team", "support_team"]
}
```

### 3. **Better Monitoring**
```python
# Easy to monitor single-table adapter performance
metrics = {
    "customer-profiles": {
        "avg_query_time": "150ms",
        "cache_hit_rate": "85%",
        "daily_queries": 1250
    }
}
```

## When Multi-Table Adapters Are Acceptable

### 1. **Pre-approved Patterns**
```yaml
# Well-tested, optimized patterns
approved_patterns:
  - name: "user-with-last-login"
    pattern: |
      SELECT u.*, l.last_login_at 
      FROM users u 
      LEFT JOIN last_logins l ON u.id = l.user_id 
      WHERE u.id = {user_id}
    max_results: 1
    
  - name: "order-with-items"
    pattern: |
      SELECT o.*, oi.product_name, oi.quantity
      FROM orders o
      INNER JOIN order_items oi ON o.id = oi.order_id
      WHERE o.id = {order_id}
    max_results: 50
```

### 2. **Materialized Views for Complex Data**
```sql
-- Create optimized views for complex queries
CREATE MATERIALIZED VIEW customer_order_summary AS
SELECT 
    c.id,
    c.name,
    COUNT(o.id) as total_orders,
    SUM(o.total) as total_spent,
    MAX(o.created_at) as last_order_date
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id
GROUP BY c.id, c.name;

-- Refresh periodically
REFRESH MATERIALIZED VIEW customer_order_summary;
```

### 3. **Federated Queries (Advanced)**
```yaml
# Combine results from multiple single-table adapters
- name: "customer-360-view"
  type: "federated_retriever"
  sources:
    - adapter: "customer-profiles"
      weight: 0.4
    - adapter: "customer-orders"  
      weight: 0.3
    - adapter: "customer-support-history"
      weight: 0.3
  config:
    merge_strategy: "entity_based"
    merge_key: "customer_id"
    max_total_results: 100
```

## Migration Strategy

### Phase 1: Audit Existing Adapters
```python
# Analyze current adapter complexity
def audit_adapters():
    for adapter in existing_adapters:
        if adapter.has_joins():
            print(f"⚠️  {adapter.name} uses JOINs - consider splitting")
        if adapter.max_results > 500:
            print(f"⚠️  {adapter.name} allows too many results")
        if not adapter.has_timeout():
            print(f"⚠️  {adapter.name} lacks query timeout")
```

### Phase 2: Split Complex Adapters
```yaml
# Before: Complex multi-table adapter
- name: "customer-everything"
  query: "SELECT * FROM customers c JOIN orders o ON c.id = o.customer_id JOIN..."

# After: Multiple focused adapters
- name: "customer-profiles"
  table: "customers"
  
- name: "customer-orders"
  table: "orders"
  security_filter: "customer_id = {user.customer_id}"
  
- name: "customer-summary"
  table: "customer_summary_mv"  # Materialized view
```

### Phase 3: Implement Safeguards
```python
# Add runtime query monitoring
class QueryMonitor:
    def before_query(self, adapter_name: str, query: str):
        if self.is_expensive_query(query):
            logger.warning(f"Expensive query detected in {adapter_name}")
            
    def after_query(self, adapter_name: str, execution_time: float, row_count: int):
        if execution_time > 5.0:  # 5 seconds
            logger.error(f"Slow query in {adapter_name}: {execution_time}s")
        if row_count > 1000:
            logger.warning(f"Large result set in {adapter_name}: {row_count} rows")
```

## Best Practices Summary

### ✅ **Do This**
- **Single table per adapter** for most use cases
- **Hard limits** on results and query time
- **Required parameters** for any multi-table queries
- **Materialized views** for complex aggregations
- **Caching** at the table level
- **Clear naming** that reflects the data scope

### ❌ **Avoid This**
- **Open-ended JOINs** without filters
- **Missing LIMIT clauses** 
- **Queries without WHERE conditions**
- **Complex subqueries** in user-defined adapters
- **Cross-schema queries** without approval
- **Adapters without timeouts**
