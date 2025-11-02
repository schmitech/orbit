# Adapter Implementation Request Template

Use this template when requesting a new adapter implementation. Fill in all relevant sections to ensure complete and accurate implementation.

## 1. Adapter Overview

### Adapter Type
- [ ] **Intent Adapter** (natural language to query translation)
- [ ] **QA Adapter** (question-answering over data)
- [ ] **File Adapter** (document search/retrieval)
- [ ] **Other**: _____________________

### Adapter Category
- [ ] **SQL-based** (PostgreSQL, MySQL, SQLite, DuckDB, SQL Server, Oracle, etc.)
- [ ] **NoSQL-based** (MongoDB, Cassandra, etc.)
- [ ] **HTTP-based** (REST APIs, GraphQL, etc.)
- [ ] **Vector-based** (Chroma, Pinecone, etc.)
- [ ] **Search-based** (Elasticsearch, OpenSearch, etc.)
- [ ] **Other**: _____________________

### Adapter Name
- **Proposed Name**: `intent-{datasource}-{domain}` (e.g., `intent-duckdb-analytics`)
- **Alternative Names**: _____________________

## 2. Datasource Configuration

### Datasource Type
- **Type**: _____________________ (e.g., `duckdb`, `postgres`, `mongodb`, `http`)
- **Is this a new datasource?** [ ] Yes [ ] No

### Connection Parameters Required
List all connection parameters needed:

```yaml
# Example structure:
datasource_name:
  host: string              # [ ] Required
  port: integer             # [ ] Required
  database: string          # [ ] Required
  username: string          # [ ] Required
  password: string          # [ ] Required
  read_only: boolean        # [ ] Required
  access_mode: string       # [ ] Required
  # Add other specific parameters
  custom_param: value
```

**Connection Requirements:**
- [ ] File-based (e.g., SQLite, DuckDB file)
- [ ] Server-based (e.g., PostgreSQL, MySQL)
- [ ] In-memory support needed
- [ ] Connection pooling required
- [ ] Read-only mode support
- [ ] Concurrent read/write access
- **Concurrency Notes**: _____________________

### Default Values
- **Default Host**: _____________________
- **Default Port**: _____________________
- **Default Database**: _____________________
- **Default Username**: _____________________
- **Other Defaults**: _____________________

## 3. Implementation Requirements

### Base Class Selection
- **SQL Intent**: `IntentSQLRetriever` → `IntentSQLiteRetriever`, `IntentPostgreSQLRetriever`, etc.
- **HTTP Intent**: `IntentHTTPRetriever` → `IntentFirecrawlRetriever`, `IntentHTTPJSONRetriever`, etc.
- **MongoDB Intent**: `IntentMongoDBRetriever` (extends `IntentHTTPRetriever`)
- **Elasticsearch Intent**: `IntentElasticsearchRetriever` (extends `IntentHTTPRetriever`)
- **Other**: _____________________

### Methods to Implement
- [ ] `create_connection()` - Connection creation logic
- [ ] `_execute_raw_query()` - Query execution (SQL adapters)
- [ ] `_execute_http_request()` - HTTP request execution (HTTP adapters)
- [ ] `_is_connection_alive()` - Connection health check
- [ ] `_close_connection()` - Connection cleanup
- [ ] `get_test_query()` - Test query for validation
- [ ] `get_default_port()` - Default port value
- [ ] `get_default_database()` - Default database value
- [ ] `get_default_username()` - Default username value
- **Additional Methods Needed**: _____________________

### Parameter Binding Format
- **SQL Adapters**: 
  - [ ] PostgreSQL-style: `%(name)s`
  - [ ] Named parameters: `:name`
  - [ ] Positional: `?`
  - **Conversion Requirements**: _____________________
- **HTTP Adapters**:
  - [ ] Query parameters
  - [ ] Path parameters
  - [ ] Request body
  - **Format**: _____________________

### Special Considerations
- [ ] Extension loading (e.g., DuckDB httpfs)
- [ ] Transaction management
- [ ] Connection pooling
- [ ] SSL/TLS configuration
- [ ] Authentication method
- **Other**: _____________________

## 4. Template Files Structure

### Template Directory Location
```
utils/{datasource}-intent-template/
├── README.md
├── docs/
│   └── {datasource}-specific-guide.md
└── examples/
    └── {domain}/
        ├── {domain}.sql                    # [ ] SQL schema (if SQL-based)
        ├── {domain}_domain.yaml            # [ ] Required
        ├── {domain}_templates.yaml         # [ ] Required
        ├── {domain}_test_queries.md        # [ ] Recommended
        ├── generate_{domain}_data.py       # [ ] Recommended
        └── test_{domain}_queries.sh         # [ ] Optional (CLI testing)
```

### Domain Configuration (`{domain}_domain.yaml`)
**Required Sections:**
- [ ] `domain_name`: Domain identifier
- [ ] `description`: Domain description
- [ ] `semantic_types`: Type definitions
- [ ] `vocabulary`: Domain-specific terms
- [ ] `entities`: Entity definitions with fields
- [ ] `relationships`: Entity relationships (if applicable)

**Entity Information Needed:**
- **Primary Entities**: _____________________
- **Key Fields per Entity**: _____________________
- **Data Types**: _____________________
- **Relationships**: _____________________

### Template Library (`{domain}_templates.yaml`)
**Template Categories Needed:**
- [ ] Basic queries (SELECT, GET, FIND)
- [ ] Filtered queries (WHERE clauses)
- [ ] Aggregated queries (COUNT, SUM, AVG, GROUP BY)
- [ ] Top-N queries (LIMIT, ORDER BY)
- [ ] Joins/Relationships
- [ ] Time-based queries (date ranges, trends)
- [ ] Complex analytical queries
- **Additional Template Types**: _____________________

**Estimated Template Count**: _____________________

## 5. Configuration Files

### `config/datasources.yaml`
**Entry Required:**
```yaml
datasource_name:
  # Connection parameters
  # Default values
  # Special settings
```

### `config/adapters.yaml`
**Adapter Entry Required:**
```yaml
- name: "intent-{datasource}-{domain}"
  enabled: true/false
  type: "retriever"
  datasource: "{datasource_name}"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.Intent{DataSource}Retriever"
  inference_provider: "{provider}"
  model: "{model_name}"
  embedding_provider: "{provider}"
  config:
    domain_config_path: "utils/{datasource}-intent-template/examples/{domain}/{domain}_domain.yaml"
    template_library_path:
      - "utils/{datasource}-intent-template/examples/{domain}/{domain}_templates.yaml"
    template_collection_name: "{collection_name}"
    store_name: "{vector_store}"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 100
    # Datasource-specific settings
```

## 6. Registration Requirements

### Files Requiring Updates
- [ ] `server/retrievers/implementations/intent/__init__.py` - Add import and export
- [ ] `server/adapters/intent/adapter.py` - Register adapter for datasource
- [ ] `server/datasources/registry.py` - Register datasource (if new)
- [ ] `server/datasources/datasource_factory.py` - Add datasource factory (if new)
- [ ] `server/services/dynamic_adapter_manager.py` - Verify adapter loading
- **Other Registration Points**: _____________________

## 7. Testing Requirements

### Unit Tests
- [ ] Create `server/tests/test_intent_{datasource}_retriever.py`
- [ ] Test connection creation
- [ ] Test query execution
- [ ] Test parameter binding
- [ ] Test connection lifecycle
- [ ] Test error handling
- [ ] Test read-only mode (if applicable)
- **Additional Test Cases**: _____________________

### Integration Tests
- [ ] End-to-end query flow
- [ ] Template matching
- [ ] Parameter extraction
- [ ] Response formatting
- **Additional Integration Tests**: _____________________

### Sample Data Generation
- [ ] Create data generation script
- [ ] Realistic sample data needed
- [ ] Data volume: _____________________ records
- **Data Generation Requirements**: _____________________

## 8. Example Use Case

### Use Case Description
**Brief Description**: _____________________

**Example Queries:**
1. _____________________
2. _____________________
3. _____________________

**Expected Behavior:**
- _____________________
- _____________________

### Domain Context
- **Business Domain**: _____________________
- **Primary Users**: _____________________
- **Common Query Patterns**: _____________________

## 9. Documentation Requirements

### Documentation Files Needed
- [ ] `README.md` - Overview and quick start
- [ ] `docs/{datasource}-specific-guide.md` - Datasource-specific features
- [ ] `examples/{domain}/{domain}_test_queries.md` - Example queries
- [ ] Code comments in implementation
- **Additional Docs**: _____________________

### Documentation Sections
- [ ] Connection configuration examples
- [ ] Parameter binding examples
- [ ] Query examples
- [ ] Troubleshooting guide
- [ ] Performance considerations
- **Additional Sections**: _____________________

## 10. Special Requirements

### Performance Considerations
- **Expected Query Volume**: _____________________
- **Response Time Targets**: _____________________
- **Caching Requirements**: _____________________

### Security Considerations
- [ ] Authentication method
- [ ] Encryption requirements
- [ ] Access control
- [ ] Data privacy
- **Additional Security**: _____________________

### Concurrency Requirements
- [ ] Multiple reader processes
- [ ] Read-only mode support
- [ ] Connection pooling
- [ ] Lock management
- **Concurrency Notes**: _____________________

### Dependencies
- **Required Python Packages**: _____________________
- **Installation Command**: `pip install _____________________`
- **Optional Dependencies**: _____________________

## 11. Implementation Checklist

Once implementation begins, track progress:

- [ ] Datasource implementation created
- [ ] Intent retriever implementation created
- [ ] Domain configuration created
- [ ] Template library created
- [ ] Configuration files updated
- [ ] Adapter registered in all required locations
- [ ] Unit tests created and passing
- [ ] Sample data generation script created
- [ ] Documentation written
- [ ] Integration tested
- [ ] Example queries validated

## 12. Additional Notes

**Any other information relevant to implementation:**

_____________________
_____________________
_____________________

---

## Example Completed Request

### Adapter Type
- [x] **Intent Adapter**
- [x] **SQL-based**
- **Proposed Name**: `intent-duckdb-analytics`

### Datasource Configuration
- **Type**: `duckdb`
- **Connection Parameters**: File-based, supports `:memory:` and file paths
- **Read-only mode**: Required for concurrent access
- **Default**: `:memory:`

### Implementation
- **Base Class**: `IntentSQLRetriever`
- **Key Features**: File-based, read-only mode, httpfs extension support

### Templates
- **Domain**: Analytics (sales, products, customers)
- **Templates**: 15+ analytical query templates

### Testing
- **Unit Tests**: 17 tests covering connection, queries, parameters
- **Sample Data**: Python script generating realistic analytics data

---

**Use this template for all future adapter implementations to ensure consistency and completeness.**
