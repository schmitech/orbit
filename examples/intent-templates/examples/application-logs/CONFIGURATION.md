# Elasticsearch Adapter Configuration Guide

This guide explains the proper separation of configuration across different files.

## Configuration Architecture

The Elasticsearch adapter uses a three-layer configuration architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Configuration Layers                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. DATASOURCE (config/datasources.yaml)                    │
│     └─> Connection details, pooling, credentials            │
│                                                               │
│  2. DOMAIN (logs_domain.yaml)                               │
│     └─> Schema, vocabulary, query patterns                  │
│                                                               │
│  3. ADAPTER (config/adapters.yaml)                          │
│     └─> Adapter settings, index overrides, templates        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: Datasource Configuration

**File**: `config/datasources.yaml`

**Purpose**: Connection parameters shared across all adapters using Elasticsearch

**Contains**:
- ✅ Elasticsearch node URL
- ✅ Authentication credentials (via environment variables)
- ✅ SSL/TLS settings
- ✅ Connection timeout
- ✅ Retry configuration

**Example**:
```yaml
datasources:
  elasticsearch:
    node: 'https://your-elastic-cloud.es.io:9200'
    verify_certs: true
    timeout: 30
    auth:
      username: ${DATASOURCE_ELASTICSEARCH_USERNAME}
      password: ${DATASOURCE_ELASTICSEARCH_PASSWORD}
```

**Why separate?**
- Multiple adapters can share the same Elasticsearch connection
- Connection pooling works at the datasource level
- Credentials are managed centrally
- Easy to switch between dev/staging/production clusters

## Layer 2: Domain Configuration

**File**: `utils/elasticsearch-intent-template/examples/application-logs/logs_domain.yaml`

**Purpose**: Domain-specific schema and knowledge about the data

**Contains**:
- ✅ Index definitions and field mappings
- ✅ Searchable fields and their types
- ✅ Vocabulary and synonyms for NLU
- ✅ Common filters and aggregations
- ✅ Query patterns and defaults
- ✅ Response formatting preferences
- ✅ Domain-specific optimization settings

**Does NOT contain**:
- ❌ Connection URLs
- ❌ Authentication credentials
- ❌ SSL settings
- ❌ Connection pooling config

**Example**:
```yaml
domain_name: "application_logs"
domain_type: "elasticsearch"
version: "1.0.0"

indices:
  application_logs:
    index_pattern: "logs-app-*"
    time_field: "timestamp"
    searchable_fields:
      - name: "message"
        type: "text"
      - name: "level"
        type: "keyword"

vocabulary:
  entity_synonyms:
    application_logs: ["logs", "log entries", "error logs"]
  action_synonyms:
    search: ["find", "show", "get", "display"]
```

**Why separate?**
- Domain knowledge is reusable across different Elasticsearch instances
- Easy to create multiple domains (logs, metrics, traces) on same cluster
- Domain files can be version controlled separately
- Domain experts can maintain these without needing connection details

## Layer 3: Adapter Configuration

**File**: `config/adapters.yaml`

**Purpose**: Adapter-specific settings and overrides

**Contains**:
- ✅ Adapter name and type
- ✅ Reference to datasource (`datasource: "elasticsearch"`)
- ✅ Domain and template paths
- ✅ Inference and embedding provider overrides
- ✅ Index pattern override (if different from domain default)
- ✅ Template matching settings (confidence, max_templates)
- ✅ Adapter-specific query settings
- ✅ Fault tolerance settings

**Does NOT contain**:
- ❌ Connection URLs (use datasource reference)
- ❌ Authentication credentials
- ❌ Domain schema definitions

**Example**:
```yaml
adapters:
  - name: "intent-elasticsearch-app-logs"
    enabled: true
    type: "retriever"
    datasource: "elasticsearch"  # References datasources.yaml
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentElasticsearchRetriever"
    inference_provider: "openai"
    embedding_provider: "openai"
    config:
      # Domain references
      domain_config_path: "utils/elasticsearch-intent-template/examples/application-logs/logs_domain.yaml"
      template_library_path:
        - "utils/elasticsearch-intent-template/examples/application-logs/logs_templates.yaml"

      # Vector store for template matching
      template_collection_name: "elasticsearch_logs_templates"
      store_name: "chroma"

      # Intent matching
      confidence_threshold: 0.4
      max_templates: 5

      # Adapter-specific Elasticsearch settings
      index_pattern: "logs-app-*"  # Can override domain default
      use_query_dsl: true
      enable_aggregations: true
      enable_highlighting: true
      default_size: 100
```

**Why separate?**
- Multiple adapters can use the same domain with different settings
- Easy to create prod/staging/dev adapters pointing to different datasources
- Adapter settings can be changed without modifying domain knowledge
- Each adapter can have its own inference/embedding provider

## Configuration Flow

```
1. Server Startup
   └─> Load config/datasources.yaml
       └─> Register Elasticsearch datasource with connection pooling

2. Adapter Request
   └─> Load config/adapters.yaml
       ├─> Get datasource reference: "elasticsearch"
       │   └─> Use pooled connection from datasource registry
       ├─> Load domain config: logs_domain.yaml
       │   └─> Get schema, vocabulary, query patterns
       └─> Load templates: logs_templates.yaml
           └─> Index templates in vector store

3. Query Execution
   └─> Use datasource connection (pooled)
   └─> Apply domain knowledge (fields, vocabulary)
   └─> Use adapter settings (index_pattern, etc.)
```

## Common Configuration Scenarios

### Scenario 1: Multiple Environments

Use different datasources, same domain:

```yaml
# config/datasources.yaml
datasources:
  elasticsearch-prod:
    node: 'https://prod-cluster.es.io:9200'
    auth: {...}

  elasticsearch-dev:
    node: 'https://dev-cluster.es.io:9200'
    auth: {...}

# config/adapters.yaml
adapters:
  - name: "logs-prod"
    datasource: "elasticsearch-prod"  # Points to prod
    config:
      domain_config_path: "utils/.../logs_domain.yaml"  # Same domain

  - name: "logs-dev"
    datasource: "elasticsearch-dev"  # Points to dev
    config:
      domain_config_path: "utils/.../logs_domain.yaml"  # Same domain
```

### Scenario 2: Multiple Domains, Same Cluster

Use same datasource, different domains:

```yaml
# config/adapters.yaml
adapters:
  - name: "logs-adapter"
    datasource: "elasticsearch"  # Same datasource
    config:
      domain_config_path: "utils/.../logs_domain.yaml"
      index_pattern: "logs-*"

  - name: "metrics-adapter"
    datasource: "elasticsearch"  # Same datasource, shared connection
    config:
      domain_config_path: "utils/.../metrics_domain.yaml"
      index_pattern: "metrics-*"
```

### Scenario 3: Index Override

Domain defines default, adapter overrides:

```yaml
# logs_domain.yaml
indices:
  application_logs:
    index_pattern: "logs-app-*"  # Default

# config/adapters.yaml
adapters:
  - name: "logs-production"
    config:
      index_pattern: "logs-app-production-*"  # Override for this adapter

  - name: "logs-all"
    config:
      # No override, uses domain default: "logs-app-*"
```

## Best Practices

### ✅ DO

1. **Keep connection details in datasources.yaml**
   - Easy credential rotation
   - Shared connection pooling
   - Environment-specific configs

2. **Keep domain knowledge in domain files**
   - Reusable across environments
   - Version controlled separately
   - Maintained by domain experts

3. **Use adapter config for overrides**
   - Per-adapter index patterns
   - Different inference providers
   - Specific query settings

4. **Use environment variables for secrets**
   ```yaml
   datasources:
     elasticsearch:
       auth:
         username: ${DATASOURCE_ELASTICSEARCH_USERNAME}
         password: ${DATASOURCE_ELASTICSEARCH_PASSWORD}
   ```

### ❌ DON'T

1. **Don't put connection details in domain files**
   ```yaml
   # ❌ BAD - Don't do this in logs_domain.yaml
   elasticsearch_config:
     base_url: "http://localhost:9200"
     username: "elastic"
   ```

2. **Don't put domain schema in adapter config**
   ```yaml
   # ❌ BAD - Don't do this in adapters.yaml
   config:
     searchable_fields:
       - name: "message"
         type: "text"
   ```

3. **Don't duplicate connection settings**
   ```yaml
   # ❌ BAD - Don't specify connection in multiple places
   ```

## Configuration Validation

Use these commands to validate your configuration:

```bash
# Test datasource connection
python utils/elasticsearch-intent-template/validate_data.py

# Generate sample data (tests datasource + adapter)
python utils/elasticsearch-intent-template/generate_sample_data.py --count 10

# Test adapter through ORBIT API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: your-key" \
  -d '{"model": "intent-elasticsearch-app-logs", "messages": [...]}'
```

## Troubleshooting

### Connection Issues
**Problem**: Cannot connect to Elasticsearch

**Check**:
1. `config/datasources.yaml` - Verify node URL
2. Environment variables are set
3. Network connectivity to cluster

### Index Not Found
**Problem**: Index pattern doesn't match any indices

**Check**:
1. Adapter `index_pattern` in `config/adapters.yaml`
2. Default pattern in `logs_domain.yaml`
3. Actual indices in Elasticsearch: `GET /_cat/indices`

### Template Matching Issues
**Problem**: Natural language queries not matching templates

**Check**:
1. Template collection name matches in adapter config
2. Templates loaded successfully (check logs)
3. Confidence threshold not too high
4. Domain vocabulary includes query terms

## Summary

| Configuration | File | Purpose | Contains |
|--------------|------|---------|----------|
| **Datasource** | `config/datasources.yaml` | Connection | URL, auth, SSL, pooling |
| **Domain** | `logs_domain.yaml` | Schema & Knowledge | Fields, vocabulary, patterns |
| **Adapter** | `config/adapters.yaml` | Adapter Settings | Templates, overrides, inference |

**Remember**: Connection → Datasource, Schema → Domain, Settings → Adapter
