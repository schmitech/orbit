# Elasticsearch Intent Template System

## Overview

This directory contains tools and examples for creating Elasticsearch intent templates that translate natural language queries into Elasticsearch Query DSL. The template system enables non-technical users to query Elasticsearch data using natural language while maintaining the full power of Elasticsearch's query capabilities.

## Quick Start

### 0. Generate Sample Data (Optional but Recommended)

Before querying, generate realistic sample data:

```bash
# Set Elasticsearch credentials
export DATASOURCE_ELASTICSEARCH_USERNAME=elastic
export DATASOURCE_ELASTICSEARCH_PASSWORD=your-password

# Generate 1000 sample logs
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 1000 \
    --index logs-app-demo

# Validate the data
python utils/elasticsearch-intent-template/validate_data.py --index logs-app-demo
```

See [SAMPLE_DATA.md](SAMPLE_DATA.md) for detailed instructions on generating sample data.

### 1. Configure Your Elasticsearch Adapter

Add to `config/adapters.yaml`:

```yaml
adapters:
  - name: "intent-elasticsearch-app-logs"
    enabled: true
    type: "retriever"
    datasource: "elasticsearch"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentElasticsearchRetriever"
    inference_provider: "openai"
    embedding_provider: "openai"
    config:
      domain_config_path: "utils/elasticsearch-intent-template/examples/application-logs/logs_domain.yaml"
      template_library_path:
        - "utils/elasticsearch-intent-template/examples/application-logs/logs_templates.yaml"
      template_collection_name: "elasticsearch_logs_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      index_pattern: "logs-app-*"
      base_url: "http://localhost:9200"
      auth:
        type: "basic_auth"
        username_env: "ES_USERNAME"
        password_env: "ES_PASSWORD"
```

### 2. Set Environment Variables

```bash
export ES_USERNAME=elastic
export ES_PASSWORD=your-password
```

### 3. Use Natural Language Queries

```
"Show me error logs from the last hour"
"How many errors by service?"
"Find slow API requests"
"Show me error trends over time"
```

## Directory Structure

```
elasticsearch-intent-template/
├── README.md                           # This file
├── examples/
│   └── application-logs/
│       ├── logs_domain.yaml           # Domain configuration
│       └── logs_templates.yaml        # Query templates
```

## Template Structure

### Domain Configuration

The domain configuration (`logs_domain.yaml`) defines:
- Elasticsearch connection settings
- Index patterns and mappings
- Authentication configuration
- Searchable fields and their types
- Common filters and aggregations
- Natural language vocabulary
- Default query patterns

Example:
```yaml
domain_name: "application_logs"
domain_type: "elasticsearch"

elasticsearch_config:
  base_url: "http://localhost:9200"
  api_version: "8.x"

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

### Query Templates

Query templates (`logs_templates.yaml`) define:
- Natural language to Query DSL mappings
- Template parameters and their types
- Elasticsearch endpoint and method
- Response formatting instructions
- Natural language examples for matching

Example:
```yaml
templates:
  - id: search_error_logs_recent
    description: "Search for recent error logs"
    index: "logs-app-*"
    endpoint_type: "_search"

    query_dsl: |
      {
        "query": {
          "bool": {
            "must": [{"match": {"level": "ERROR"}}],
            "filter": [{
              "range": {
                "timestamp": {
                  "gte": "{{start_time}}",
                  "lte": "{{end_time}}"
                }
              }
            }]
          }
        }
      }

    parameters:
      - name: start_time
        type: string
        default: "now-24h"

    nl_examples:
      - "Show me recent error logs"
      - "Find errors in the last 24 hours"
```

## Supported Query Types

### 1. Search Queries
- Full-text search
- Term queries
- Range queries
- Wildcard queries
- Boolean combinations

### 2. Aggregations
- Terms aggregations
- Date histogram
- Metrics (avg, sum, min, max, percentiles)
- Nested aggregations
- Pipeline aggregations

### 3. Special Features
- Highlighting
- Sorting
- Pagination
- Field filtering
- Source filtering

## Creating Custom Templates

### Step 1: Analyze Your Index

```bash
# Get index mapping
curl -X GET "localhost:9200/your-index/_mapping"

# Sample documents
curl -X GET "localhost:9200/your-index/_search?size=5"
```

### Step 2: Define Domain Configuration

Create `your_domain.yaml`:
```yaml
domain_name: "your_domain"
domain_type: "elasticsearch"

elasticsearch_config:
  base_url: "http://localhost:9200"

indices:
  your_index:
    index_pattern: "your-index-*"
    searchable_fields:
      - name: "field1"
        type: "text"
      - name: "field2"
        type: "keyword"

vocabulary:
  entity_synonyms:
    your_index: ["items", "records", "entries"]
```

### Step 3: Create Query Templates

Create `your_templates.yaml`:
```yaml
templates:
  - id: search_your_index
    description: "Search your index"
    index: "your-index-*"

    query_dsl: |
      {
        "query": {
          "match": {
            "field1": "{{search_term}}"
          }
        }
      }

    parameters:
      - name: search_term
        type: string
        required: true

    nl_examples:
      - "Search for items"
      - "Find records"
```

### Step 4: Update Configuration

Add your adapter to `config/adapters.yaml` pointing to your domain and templates.

## Template Best Practices

### 1. Use Descriptive IDs
```yaml
# Good
id: search_error_logs_by_user

# Bad
id: search1
```

### 2. Provide Multiple Natural Language Examples
```yaml
nl_examples:
  - "Show me errors for user john"
  - "Find error logs by user john"
  - "What errors did user john encounter?"
  - "Get john's error logs"
```

### 3. Use Semantic Tags
```yaml
semantic_tags:
  action: "search"
  primary_entity: "error_logs"
  qualifiers: ["user", "filter"]
  time_based: true
```

### 4. Document Parameters
```yaml
parameters:
  - name: user_id
    type: string
    required: false
    description: "User ID to filter by"
    example: "user123"
    location: "body"
```

### 5. Use Conditional Logic
```yaml
query_dsl: |
  {
    "query": {
      "bool": {
        "must": [
          {% if search_term %}
          {"match": {"message": "{{search_term}}"}}
          {% endif %}
        ]
      }
    }
  }
```

## Common Patterns

### Pattern 1: Time-Range Queries
```yaml
query_dsl: |
  {
    "query": {
      "range": {
        "timestamp": {
          "gte": "{{start_time}}",
          "lte": "{{end_time}}"
        }
      }
    }
  }
```

### Pattern 2: Aggregations
```yaml
query_dsl: |
  {
    "size": 0,
    "aggs": {
      "by_field": {
        "terms": {
          "field": "{{field_name}}",
          "size": {{agg_size}}
        }
      }
    }
  }
```

### Pattern 3: Full-Text Search with Filters
```yaml
query_dsl: |
  {
    "query": {
      "bool": {
        "must": [
          {"match": {"message": "{{query}}"}}
        ],
        "filter": [
          {"term": {"status": "{{status}}"}}
        ]
      }
    }
  }
```

## Troubleshooting

### Templates Not Matching
1. Check natural language examples are diverse
2. Verify semantic tags are accurate
3. Lower confidence threshold in config
4. Check template collection name matches

### Query Execution Errors
1. Verify Elasticsearch is running and accessible
2. Check authentication credentials
3. Validate Query DSL syntax with curl
4. Review parameter extraction logic

### No Results Returned
1. Verify index pattern matches existing indices
2. Check time range parameters
3. Test query directly against Elasticsearch
4. Review field mappings

## Examples

### Example 1: Error Log Search
```
Natural Language: "Show me production errors from the last hour"

Generated Query DSL:
{
  "query": {
    "bool": {
      "must": [{"match": {"level": "ERROR"}}],
      "filter": [
        {"term": {"environment": "production"}},
        {"range": {"timestamp": {"gte": "now-1h", "lte": "now"}}}
      ]
    }
  }
}
```

### Example 2: Error Aggregation
```
Natural Language: "How many errors by service?"

Generated Query DSL:
{
  "size": 0,
  "aggs": {
    "by_service": {
      "terms": {
        "field": "service_name",
        "size": 20
      }
    }
  }
}
```

### Example 3: Performance Analysis
```
Natural Language: "Find slow requests in the last 24 hours"

Generated Query DSL:
{
  "query": {
    "bool": {
      "filter": [
        {"range": {"response_time": {"gte": 1000}}},
        {"range": {"timestamp": {"gte": "now-24h"}}}
      ]
    }
  },
  "sort": [{"response_time": {"order": "desc"}}]
}
```

## Advanced Features

### Multi-Index Queries
```yaml
index: "logs-*,metrics-*"  # Query multiple indices
```

### Nested Aggregations
```yaml
aggs:
  by_service:
    terms:
      field: service_name
    aggs:
      by_level:
        terms:
          field: level
```

### Highlighting
```yaml
highlight:
  fields:
    message:
      fragment_size: 150
      number_of_fragments: 3
```

### Source Filtering
```yaml
_source:
  includes: ["field1", "field2"]
  excludes: ["internal_*"]
```

## Resources

- [Elasticsearch Query DSL Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Elasticsearch Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [ORBIT Documentation](../../docs/)
- [Implementation Summary](../../docs/elasticsearch-adapter-implementation.md)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the implementation documentation
3. Check Elasticsearch logs
4. Verify configuration files are valid YAML

## Contributing

To add new templates:
1. Create template following the patterns above
2. Add diverse natural language examples
3. Test with real queries
4. Document any special requirements
5. Add to appropriate template library file

## License

Same as ORBIT project license.
