## Implementation Plan: IntentKnowledgeGraphRetriever

### Phase 1: Base Architecture

#### 1.1 Create Base Knowledge Graph Retriever

**File**: `server/retrievers/base/intent_kg_base.py`

- Extend `BaseRetriever` (similar to `IntentSQLRetriever` and `IntentHTTPRetriever`)
- Implement common graph query patterns:
    - Entity lookup
    - Relationship traversal
    - Multi-hop path queries
    - Graph pattern matching
- Integrate with existing intent system:
    - Template matching via vector store
    - Domain parameter extraction
    - Response generation
- Support Cypher/Gremlin query translation from templates

**Key Methods**:

```python
class IntentKnowledgeGraphRetriever(BaseRetriever):
    async def initialize(self) -> None
    async def _execute_graph_query(self, template: Dict, parameters: Dict) -> Tuple[Any, Optional[str]]
    async def _format_graph_results(self, results: Any, template: Dict) -> List[Dict[str, Any]]
    def _translate_template_to_query(self, template: Dict, parameters: Dict) -> str
    async def get_relevant_context(self, query: str, **kwargs) -> List[Dict[str, Any]]
```

#### 1.2 Create Graph Query Template Format

**File**: `utils/kg-intent-template/examples/customer-orders/kg_domain.yaml`

- Define graph schema (nodes, relationships, properties)
- Create Cypher/Gremlin query templates
- Support parameterized graph queries
- Define relationship traversal patterns

**Template Structure**:

```yaml
templates:
 - id: "find_customer_orders"
    description: "Find orders for a customer"
    nl_examples:
   - "Show orders for customer John"
   - "What orders does customer 123 have?"
    parameters:
   - name: "customer_id"
        type: "string"
        required: true
    cypher: |
      MATCH (c:Customer {id: $customer_id})-[:PLACED]->(o:Order)
      RETURN o, c
    gremlin: |
      g.V().has('Customer', 'id', customer_id)
        .out('PLACED')
        .valueMap()
```

### Phase 2: Neo4j Implementation

#### 2.1 Create Neo4j Datasource

**File**: `server/datasources/implementations/neo4j_datasource.py`

- Implement `BaseDatasource` interface
- Support Neo4j driver (async)
- Connection pooling
- Authentication (username/password, auth token)
- Support both HTTP and Bolt protocols

**Configuration** (`config/datasources.yaml`):

```yaml
neo4j:
  uri: ${DATASOURCE_NEO4J_URI}  # bolt://localhost:7687 or neo4j://localhost:7687
  username: ${DATASOURCE_NEO4J_USERNAME}
  password: ${DATASOURCE_NEO4J_PASSWORD}
  database: ${DATASOURCE_NEO4J_DATABASE}  # Optional, defaults to 'neo4j'
  max_connection_pool_size: 50
  connection_timeout: 30
  encrypted: true  # Use TLS
  trust: "TRUST_SYSTEM_CA_SIGNED_CERTIFICATES"
```

#### 2.2 Create Neo4j Intent Retriever

**File**: `server/retrievers/implementations/intent/intent_neo4j_retriever.py`

- Extend `IntentKnowledgeGraphRetriever`
- Implement Cypher query execution
- Handle Neo4j result format
- Support transaction management
- Error handling for Neo4j-specific errors

**Key Features**:

- Cypher query translation from templates
- Parameter binding
- Result formatting (nodes, relationships, paths)
- Support for graph patterns and aggregations

#### 2.3 Create Example Domain Configuration

**File**: `utils/kg-intent-template/examples/customer-orders/kg_domain.yaml`

- Define customer-order graph schema
- Create example templates for common queries
- Include relationship definitions

**Example Schema**:

```yaml
domain_name: "Customer Orders Knowledge Graph"
description: "Customer and order management with graph relationships"

graph_schema:
  nodes:
  - label: "Customer"
      properties:
    - name: "id"
          type: "string"
          required: true
    - name: "name"
          type: "string"
  - label: "Order"
      properties:
    - name: "id"
          type: "string"
          required: true
    - name: "total"
          type: "float"
  relationships:
  - type: "PLACED"
      from: "Customer"
      to: "Order"
```

### Phase 3: Amazon Neptune Implementation

#### 3.1 Create Neptune Datasource

**File**: `server/datasources/implementations/neptune_datasource.py`

- Implement `BaseDatasource` interface
- Support both Gremlin and SPARQL protocols
- AWS authentication (IAM, SigV4)
- Connection pooling for Neptune
- Support for Neptune cluster endpoints

**Configuration** (`config/datasources.yaml`):

```yaml
neptune:
  endpoint: ${DATASOURCE_NEPTUNE_ENDPOINT}
  port: ${DATASOURCE_NEPTUNE_PORT}  # 8182 for Gremlin
  region: ${DATASOURCE_NEPTUNE_REGION}
  query_language: "gremlin"  # gremlin or sparql
  use_ssl: true
  auth:
    type: "iam"  # iam or none
  connection_pool_size: 10
  connection_timeout: 30
```

#### 3.2 Create Neptune Intent Retriever

**File**: `server/retrievers/implementations/intent/intent_neptune_retriever.py`

- Extend `IntentKnowledgeGraphRetriever`
- Support Gremlin query execution (primary)
- Optional SPARQL support
- Handle Neptune result format
- AWS SigV4 signing for requests

### Phase 4: Adapter Configuration

#### 4.1 Add Neo4j Adapter Configuration

**File**: `config/adapters.yaml`

```yaml
 - name: "intent-kg-neo4j-customer-orders"
    enabled: true
    type: "retriever"
    datasource: "neo4j"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.intent_neo4j_retriever.IntentNeo4jRetriever"
    inference_provider: "ollama_cloud"
    model: "kimi-k2-thinking:cloud"
    embedding_provider: "openai"
    
    config:
      domain_config_path: "utils/kg-intent-template/examples/customer-orders/kg_domain.yaml"
      template_library_path:
    - "utils/kg-intent-template/examples/customer-orders/kg_templates.yaml"
      template_collection_name: "neo4j_customer_orders_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      max_templates: 5
      return_results: 10
```

#### 4.2 Add Neptune Adapter Configuration

**File**: `config/adapters.yaml`

Similar structure to Neo4j but with Neptune-specific settings.

### Phase 5: Example Templates and Data

#### 5.1 Create Example Graph Templates

**File**: `utils/kg-intent-template/examples/customer-orders/kg_templates.yaml`

- Templates for common graph queries
- Support both Cypher (Neo4j) and Gremlin (Neptune)
- Multi-hop relationship examples
- Entity disambiguation examples

#### 5.2 Create Sample Data Scripts

**Files**:

- `examples/neo4j/sample-data-setup.py`
- `examples/neptune/sample-data-setup.py`

- Scripts to populate graph databases with sample data
- Customer-order-product relationships
- Can be run to set up example graph

### Phase 6: Documentation

#### 6.1 Create Knowledge Graph Retriever Guide

**File**: `docs/knowledge-graph-retriever-guide.md`

- Overview of knowledge graph retrieval
- When to use KG vs SQL/vector retrieval
- Configuration guide
- Example use cases
- Graph schema design best practices

#### 6.2 Update Adapter Documentation

**File**: `docs/adapters/adapters.md`

- Add knowledge graph retriever to available implementations
- Document Neo4j and Neptune configurations
- Provide examples

### Phase 7: Testing and Validation

#### 7.1 Unit Tests

**Files**:

- `server/retrievers/implementations/intent/test_intent_neo4j_retriever.py`
- `server/retrievers/implementations/intent/test_intent_neptune_retriever.py`

- Test query translation
- Test parameter extraction
- Test result formatting
- Test error handling

#### 7.2 Integration Tests

**File**: `server/tests/test_kg_retrievers.py`

- End-to-end tests with sample graph
- Compare results with SQL-based approach
- Test multi-hop queries
- Performance benchmarks

### Phase 8: Registration and Integration

#### 8.1 Register Datasources

**File**: `server/datasources/__init__.py`

- Add Neo4j to datasource registry
- Add Neptune to datasource registry
- Ensure auto-discovery works

#### 8.2 Register Graph Retrievers

**File**: `server/retrievers/__init__.py`

- Import and register `IntentNeo4jRetriever`
- Import and register `IntentNeptuneRetriever`
- Register with `RetrieverFactory`

## Implementation Checklist

### Core Components

- [ ] Create `IntentKnowledgeGraphRetriever` base class
- [ ] Implement `IntentNeo4jRetriever`
- [ ] Implement `IntentNeptuneRetriever`
- [ ] Create Neo4j datasource implementation
- [ ] Create Neptune datasource implementation

### Configuration

- [ ] Add Neo4j datasource config to `datasources.yaml`
- [ ] Add Neptune datasource config to `datasources.yaml`
- [ ] Add Neo4j adapter config to `adapters.yaml`
- [ ] Add Neptune adapter config to `adapters.yaml`

### Examples and Documentation

- [ ] Create example domain configuration (customer-orders)
- [ ] Create example graph templates
- [ ] Create sample data setup scripts
- [ ] Write knowledge graph retriever guide
- [ ] Update adapter documentation
- [ ] Create example README

### Testing

- [ ] Unit tests for base KG retriever
- [ ] Unit tests for Neo4j retriever
- [ ] Unit tests for Neptune retriever
- [ ] Integration tests
- [ ] Example queries validation

### Registration

- [ ] Register Neo4j datasource
- [ ] Register Neptune datasource
- [ ] Register graph retrievers with factory

## Dependencies

### Python Packages

- `neo4j` - Neo4j Python driver
- `gremlinpython` - Gremlin Python client (for Neptune)
- `boto3` - AWS SDK (for Neptune IAM auth)