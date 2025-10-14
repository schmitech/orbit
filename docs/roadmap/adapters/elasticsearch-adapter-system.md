# Elasticsearch Adapter System Roadmap

## Overview

This roadmap outlines the strategic implementation of an Elasticsearch adapter system for ORBIT, designed to enable seamless integration with Elasticsearch and other search engine platforms (OpenSearch, Solr) for log analysis, full-text search, and real-time analytics. The system will follow the same template-based architecture as the existing SQL and HTTP intent adapters, providing a consistent framework for natural language to Elasticsearch Query DSL translation.

**Key Insight**: The Elasticsearch adapter system **inherits from `IntentHTTPRetriever`** since Elasticsearch uses HTTP transport, but adds specialized Query DSL generation, aggregation support, and search-specific features.

**Architecture Decision**:
- **Base Class**: `IntentHTTPRetriever` (reuses HTTP infrastructure)
- **Specialization**: Elasticsearch Query DSL generation, aggregation handling, index management
- **Pattern**: Similar to how `IntentSQLiteRetriever` extends `IntentSQLRetriever` - same base, different query language

## Strategic Goals

- **Unified Search Interface**: Create a consistent abstraction layer for Elasticsearch and compatible search engines
- **Template-Driven Query DSL**: Leverage YAML templates for Elasticsearch query definitions with variable substitution
- **Intent-Based Search**: Natural language to Elasticsearch Query DSL translation using vector similarity matching
- **Full-Text Search**: Advanced text search capabilities with relevance scoring and highlighting
- **Real-Time Analytics**: Support for aggregations, metrics, and time-series analysis
- **Log Analysis**: Specialized support for application log querying and troubleshooting
- **Performance Optimization**: Efficient query execution with caching and connection pooling
- **Automated Template Generation**: Tools to generate Elasticsearch templates from index mappings

## Use Cases

### Primary Use Cases
1. **Application Log Analysis**: Query application logs for errors, warnings, debugging
2. **Full-Text Search**: Search documents, articles, product catalogs
3. **Metrics & Analytics**: Time-series data analysis, aggregations, statistics
4. **Security & Audit Logs**: SIEM-like queries for security event analysis
5. **User Activity Tracking**: Analyze user behavior, clickstream data
6. **System Monitoring**: Infrastructure metrics, performance monitoring

### Example Natural Language Queries
- "Show me errors from the last hour"
- "Find all 500 errors for user john123"
- "How many requests per service in the last 24 hours?"
- "What's the average response time by endpoint?"
- "Search for 'authentication failure' in logs"
- "Show me the top 10 error messages today"

## Phase 1: Foundation & Core Architecture

### 1.1 Elasticsearch Retriever Layer

**Objective**: Implement the Elasticsearch intent retriever that inherits from `IntentHTTPRetriever`

**Deliverables**:
- `IntentElasticsearchRetriever` class extending `IntentHTTPRetriever`
- Elasticsearch Query DSL template processing
- Vector store integration for template matching
- Response parsing for hits, aggregations, and highlights
- Index and mapping management

**Key Components**:
```python
# server/retrievers/implementations/intent/intent_elasticsearch_retriever.py
class IntentElasticsearchRetriever(IntentHTTPRetriever):
    """
    Elasticsearch-specific intent retriever.
    Translates natural language queries to Elasticsearch Query DSL.
    Inherits HTTP transport from IntentHTTPRetriever.
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, **kwargs):
        """Initialize Elasticsearch retriever with HTTP base."""
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)

        # Elasticsearch-specific settings
        self.index_pattern = config.get('index_pattern', '*')
        self.use_query_dsl = config.get('use_query_dsl', True)
        self.enable_aggregations = config.get('enable_aggregations', True)
        self.enable_highlighting = config.get('enable_highlighting', True)
        self.default_size = config.get('default_size', 100)

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "elasticsearch"

    # Override: Process Elasticsearch Query DSL templates
    def _process_http_template(self, template: str, parameters: Dict) -> Dict[str, Any]:
        """
        Process Elasticsearch Query DSL template with variable substitution.
        Returns: Complete Elasticsearch query object (not a URL string)
        """
        query_dsl = self._render_query_dsl(template, parameters)
        return query_dsl

    def _render_query_dsl(self, template: str, parameters: Dict) -> Dict:
        """Render Elasticsearch Query DSL with parameters."""
        if self.template_processor:
            rendered = self.template_processor.render_sql(
                template,
                parameters=parameters,
                preserve_unknown=False
            )
            return json.loads(rendered)
        return {}

    # Override: Build Elasticsearch-specific HTTP request
    async def _build_http_request(self, template: Dict, parameters: Dict) -> Dict[str, Any]:
        """
        Build Elasticsearch API request.
        Constructs the HTTP request with Query DSL in the body.
        """
        # Get Query DSL from template
        query_dsl_template = template.get('query_dsl', template.get('elasticsearch_query'))
        query_dsl = self._process_http_template(query_dsl_template, parameters)

        # Determine index and endpoint
        index = template.get('index', self.index_pattern)
        endpoint_type = template.get('endpoint_type', '_search')  # _search, _count, _msearch
        endpoint = template.get('endpoint', f"/{index}/{endpoint_type}")

        # Build request
        request = {
            'method': template.get('http_method', 'POST'),
            'url': f"{self.base_url}{endpoint}",
            'headers': {
                'Content-Type': 'application/json',
                **self._build_auth_headers(template)
            },
            'json': query_dsl,
            'timeout': template.get('timeout', 30)
        }

        return request

    # Override: Handle Elasticsearch-specific response format
    def _format_http_response(self, response: Any, template: Dict) -> List[Dict[str, Any]]:
        """
        Format Elasticsearch response.
        Handles hits, aggregations, highlights, and suggestions.
        """
        response_json = response.json()

        # Extract components
        hits = self._extract_hits(response_json)
        aggregations = self._extract_aggregations(response_json)
        suggestions = self._extract_suggestions(response_json)

        # Format as human-readable text
        content = self._format_elasticsearch_results(hits, aggregations, suggestions, template)

        # Build response
        formatted = [{
            "content": content,
            "metadata": {
                "source": "elasticsearch",
                "template_id": template.get('id'),
                "index": template.get('index'),
                "result_count": len(hits),
                "total_hits": response_json.get('hits', {}).get('total', {}).get('value', 0),
                "took_ms": response_json.get('took', 0),
                "timed_out": response_json.get('timed_out', False),
                "max_score": response_json.get('hits', {}).get('max_score'),
                "results": hits,
                "aggregations": aggregations,
                "suggestions": suggestions
            },
            "confidence": template.get('confidence', 0.8)
        }]

        return formatted

    # Elasticsearch-specific helper methods
    def _extract_hits(self, response: Dict) -> List[Dict]:
        """Extract and format search hits."""
        hits = response.get('hits', {}).get('hits', [])
        results = []

        for hit in hits:
            result = {
                '_index': hit.get('_index'),
                '_id': hit.get('_id'),
                '_score': hit.get('_score'),
                **hit.get('_source', {})
            }

            # Add highlights if present
            if 'highlight' in hit:
                result['_highlights'] = hit['highlight']

            results.append(result)

        return results

    def _extract_aggregations(self, response: Dict) -> Dict:
        """Extract aggregation results."""
        return response.get('aggregations', {})

    def _extract_suggestions(self, response: Dict) -> Dict:
        """Extract search suggestions."""
        return response.get('suggest', {})

    def _format_elasticsearch_results(self, hits: List, aggs: Dict, suggests: Dict, template: Dict) -> str:
        """Format Elasticsearch results as human-readable text."""
        lines = []

        # Format hits
        if hits:
            total = len(hits)
            lines.append(f"Found {total} results:")

            display_fields = template.get('display_fields', None)

            for i, hit in enumerate(hits[:10], 1):
                lines.append(f"\n{i}. (Score: {hit.get('_score', 'N/A')})")

                if display_fields:
                    for field in display_fields:
                        if field in hit:
                            lines.append(f"   {field}: {hit[field]}")
                else:
                    # Show all non-internal fields
                    for key, value in hit.items():
                        if not key.startswith('_'):
                            lines.append(f"   {key}: {value}")

                # Add highlights
                if '_highlights' in hit:
                    lines.append("   Highlights:")
                    for field, highlights in hit['_highlights'].items():
                        lines.append(f"     {field}: {highlights[0]}")

            if total > 10:
                lines.append(f"\n... and {total - 10} more results")
        else:
            lines.append("No results found.")

        # Format aggregations
        if aggs:
            lines.append("\n\nAggregations:")
            for agg_name, agg_data in aggs.items():
                lines.append(f"\n{agg_name}:")

                if 'buckets' in agg_data:
                    for bucket in agg_data['buckets'][:10]:
                        key = bucket.get('key', bucket.get('key_as_string', 'Unknown'))
                        doc_count = bucket.get('doc_count', 0)
                        lines.append(f"  {key}: {doc_count}")
                elif 'value' in agg_data:
                    lines.append(f"  Value: {agg_data['value']}")

        # Format suggestions
        if suggests:
            lines.append("\n\nSuggestions:")
            for suggest_name, suggest_data in suggests.items():
                for suggestion in suggest_data:
                    lines.append(f"  {suggest_name}: {suggestion.get('text', '')}")

        return '\n'.join(lines)

    async def _execute_count_query(self, query_dsl: Dict, index: str) -> int:
        """Execute a count query to get total matching documents."""
        endpoint = f"/{index}/_count"
        response = await self._execute_http_request({
            'method': 'POST',
            'url': f"{self.base_url}{endpoint}",
            'json': query_dsl
        })
        return response.json().get('count', 0)

    async def get_index_mapping(self, index: str) -> Dict:
        """Get index mapping for template generation."""
        endpoint = f"/{index}/_mapping"
        response = await self._execute_http_request({
            'method': 'GET',
            'url': f"{self.base_url}{endpoint}"
        })
        return response.json()

# Register the Elasticsearch retriever
RetrieverFactory.register_retriever('intent_elasticsearch', IntentElasticsearchRetriever)
```

### 1.2 Elasticsearch Domain Configuration

**Objective**: Define Elasticsearch-specific domain configuration structure

**Domain Configuration Structure**:
```yaml
# utils/elasticsearch-intent-template/examples/application-logs/logs_domain.yaml
domain_name: "application_logs"
domain_type: "elasticsearch"
version: "1.0.0"

# Elasticsearch Connection Configuration
elasticsearch_config:
  base_url: "http://localhost:9200"
  api_version: "8.x"
  use_ssl: false
  verify_certs: false
  default_timeout: 30
  scroll_timeout: "5m"

  # Connection pooling
  pool_size: 10
  max_retries: 3
  retry_on_timeout: true

# Authentication Configuration
authentication:
  type: "basic_auth"  # basic_auth, api_key, bearer_token
  username_env: "ES_USERNAME"
  password_env: "ES_PASSWORD"
  # For API key auth:
  # api_key_id_env: "ES_API_KEY_ID"
  # api_key_env: "ES_API_KEY"

# Index/Entity Definitions (analogous to SQL tables)
indices:
  application_logs:
    # Index pattern (supports wildcards)
    index_pattern: "logs-app-*"

    # Primary identifier
    primary_key: "_id"
    display_name: "Application Logs"
    display_name_field: "message"

    # Time field for time-based queries
    time_field: "timestamp"
    time_field_format: "strict_date_optional_time"

    # Searchable fields (mapped fields in Elasticsearch)
    searchable_fields:
      - name: "message"
        type: "text"
        analyzer: "standard"
      - name: "level"
        type: "keyword"
      - name: "logger"
        type: "keyword"
      - name: "exception.message"
        type: "text"
      - name: "exception.stacktrace"
        type: "text"
      - name: "user_id"
        type: "keyword"
      - name: "request_id"
        type: "keyword"
      - name: "service_name"
        type: "keyword"
      - name: "environment"
        type: "keyword"
      - name: "host"
        type: "keyword"
      - name: "response_time"
        type: "integer"
      - name: "status_code"
        type: "integer"

    # Common filters
    common_filters:
      - field: "level"
        type: "term"
        values: ["ERROR", "WARN", "INFO", "DEBUG", "TRACE"]
      - field: "environment"
        type: "term"
        values: ["production", "staging", "development"]
      - field: "service_name"
        type: "term"
      - field: "status_code"
        type: "range"
        ranges:
          - "200-299"  # Success
          - "400-499"  # Client errors
          - "500-599"  # Server errors

    # Common aggregations
    common_aggregations:
      - name: "errors_by_level"
        type: "terms"
        field: "level"
        size: 10

      - name: "errors_by_service"
        type: "terms"
        field: "service_name"
        size: 20

      - name: "errors_over_time"
        type: "date_histogram"
        field: "timestamp"
        calendar_interval: "1h"

      - name: "avg_response_time"
        type: "avg"
        field: "response_time"

      - name: "percentiles_response_time"
        type: "percentiles"
        field: "response_time"
        percents: [50, 95, 99]

    # Default sorting
    default_sort:
      - field: "timestamp"
        order: "desc"

    # Highlighting configuration
    highlighting:
      enabled: true
      fields:
        - "message"
        - "exception.message"
      pre_tags: ["<mark>"]
      post_tags: ["</mark>"]
      fragment_size: 150
      number_of_fragments: 3

  metrics:
    index_pattern: "metrics-*"
    primary_key: "_id"
    display_name: "Application Metrics"
    display_name_field: "metric_name"
    time_field: "timestamp"

    searchable_fields:
      - name: "metric_name"
        type: "keyword"
      - name: "value"
        type: "float"
      - name: "service_name"
        type: "keyword"
      - name: "host"
        type: "keyword"
      - name: "tags"
        type: "keyword"

    common_aggregations:
      - name: "avg_metric_value"
        type: "avg"
        field: "value"
      - name: "max_metric_value"
        type: "max"
        field: "value"
      - name: "min_metric_value"
        type: "min"
        field: "value"
      - name: "metric_over_time"
        type: "date_histogram"
        field: "timestamp"
        calendar_interval: "5m"

# Vocabulary for Natural Language Understanding
vocabulary:
  entity_synonyms:
    application_logs: ["logs", "log entries", "application logs", "error logs", "system logs"]
    metrics: ["metrics", "measurements", "statistics", "stats", "performance data"]

  action_synonyms:
    search: ["find", "show", "get", "search", "look for", "display", "list"]
    aggregate: ["count", "sum", "average", "group", "aggregate", "summarize"]
    filter: ["filter", "where", "with", "having", "matching"]
    sort: ["sort", "order", "rank"]

  qualifier_synonyms:
    recent: ["recent", "latest", "new", "last", "current"]
    error: ["error", "exception", "failure", "problem", "crash", "bug"]
    warning: ["warning", "warn", "caution", "alert"]
    critical: ["critical", "severe", "fatal", "serious"]
    slow: ["slow", "delayed", "timeout", "performance"]

  time_expressions:
    hour: ["hour", "hr", "h"]
    day: ["day", "d"]
    week: ["week", "w"]
    month: ["month", "mo"]
    minute: ["minute", "min", "m"]

# Query DSL Patterns
query_patterns:
  # Default time range for time-based queries
  date_range:
    default_field: "timestamp"
    default_range: "now-24h"
    default_to: "now"

  # Pagination defaults
  pagination:
    default_size: 100
    max_size: 10000
    default_from: 0

  # Full-text search defaults
  text_search:
    default_operator: "AND"
    fuzziness: "AUTO"
    minimum_should_match: "75%"

  # Aggregation defaults
  aggregation:
    default_size: 10
    missing_bucket: false

# Response Processing
response_processing:
  default_format: "json"
  include_score: true
  include_highlights: true
  include_source: true
  source_includes: []  # Empty means include all
  source_excludes: []

# Performance & Optimization
performance:
  use_scroll_api: false  # For large result sets
  scroll_size: 1000
  request_cache: true
  track_total_hits: true
  max_concurrent_shard_requests: 5
```

### 1.3 Elasticsearch Template Structure

**Objective**: Define comprehensive Elasticsearch Query DSL template structure

**Template Structure**:
```yaml
# utils/elasticsearch-intent-template/examples/application-logs/logs_templates.yaml
templates:
  - id: search_error_logs_recent
    version: "1.0.0"
    description: "Search for recent error logs in application"
    category: "log_search"
    complexity: "simple"

    # Elasticsearch-specific fields
    index: "logs-app-*"
    http_method: "POST"
    endpoint: "/{index}/_search"
    endpoint_type: "_search"

    # Elasticsearch Query DSL template (with variable substitution)
    query_dsl: |
      {
        "query": {
          "bool": {
            "must": [
              {
                "match": {
                  "level": "ERROR"
                }
              }
              {% if message %}
              ,{
                "match": {
                  "message": {
                    "query": "{{message}}",
                    "operator": "and",
                    "fuzziness": "AUTO"
                  }
                }
              }
              {% endif %}
              {% if user_id %}
              ,{
                "term": {
                  "user_id": "{{user_id}}"
                }
              }
              {% endif %}
              {% if service_name %}
              ,{
                "term": {
                  "service_name": "{{service_name}}"
                }
              }
              {% endif %}
            ],
            "filter": [
              {
                "range": {
                  "timestamp": {
                    "gte": "{{start_time}}",
                    "lte": "{{end_time}}"
                  }
                }
              }
              {% if environment %}
              ,{
                "term": {
                  "environment": "{{environment}}"
                }
              }
              {% endif %}
            ]
          }
        },
        "size": {{limit}},
        "from": {{offset}},
        "sort": [
          {
            "timestamp": {
              "order": "desc"
            }
          }
        ],
        "highlight": {
          "fields": {
            "message": {
              "fragment_size": 150,
              "number_of_fragments": 3
            },
            "exception.message": {
              "fragment_size": 150
            }
          },
          "pre_tags": ["<mark>"],
          "post_tags": ["</mark>"]
        },
        "_source": {
          "includes": ["timestamp", "level", "message", "service_name", "user_id", "exception", "request_id"]
        }
      }

    # Template Parameters
    parameters:
      - name: message
        type: string
        required: false
        description: "Error message text to search for"
        location: "body"
        example: "connection timeout"

      - name: user_id
        type: string
        required: false
        description: "User ID associated with error"
        location: "body"
        example: "user123"

      - name: service_name
        type: string
        required: false
        description: "Service name that generated the log"
        location: "body"
        example: "auth-service"

      - name: environment
        type: string
        required: false
        description: "Environment (production, staging, development)"
        location: "body"
        allowed_values: ["production", "staging", "development"]

      - name: start_time
        type: string
        required: false
        default: "now-24h"
        description: "Start of time range"
        location: "body"
        format: "date_time"

      - name: end_time
        type: string
        required: false
        default: "now"
        description: "End of time range"
        location: "body"
        format: "date_time"

      - name: limit
        type: integer
        required: false
        default: 100
        description: "Maximum number of results"
        location: "body"
        min: 1
        max: 10000

      - name: offset
        type: integer
        required: false
        default: 0
        description: "Result offset for pagination"
        location: "body"
        min: 0

    # Natural Language Examples for Intent Matching
    nl_examples:
      - "Show me recent error logs"
      - "Find errors in the last 24 hours"
      - "What errors did user john123 encounter?"
      - "Search for authentication errors"
      - "Show me errors with message connection timeout"
      - "Get error logs from the auth service"
      - "Find production errors from yesterday"
      - "Show me all errors for user admin"

    # Semantic Tags for Template Matching
    semantic_tags:
      action: "search"
      primary_entity: "application_logs"
      qualifiers: ["error", "recent", "filter"]
      time_based: true

    # Display configuration
    display_fields:
      - "timestamp"
      - "level"
      - "service_name"
      - "message"
      - "user_id"

    # Tags for categorization
    tags: ["logs", "errors", "search", "recent"]
    result_format: "table"
    timeout: 30

  - id: aggregate_errors_by_service
    version: "1.0.0"
    description: "Count and group errors by service name"
    category: "log_analytics"
    complexity: "medium"

    index: "logs-app-*"
    http_method: "POST"
    endpoint: "/{index}/_search"

    query_dsl: |
      {
        "query": {
          "bool": {
            "must": [
              {
                "match": {
                  "level": "ERROR"
                }
              }
            ],
            "filter": [
              {
                "range": {
                  "timestamp": {
                    "gte": "{{start_time}}",
                    "lte": "{{end_time}}"
                  }
                }
              }
              {% if environment %}
              ,{
                "term": {
                  "environment": "{{environment}}"
                }
              }
              {% endif %}
            ]
          }
        },
        "size": 0,
        "aggs": {
          "by_service": {
            "terms": {
              "field": "service_name",
              "size": {{agg_size}},
              "order": {
                "_count": "desc"
              }
            },
            "aggs": {
              "error_types": {
                "terms": {
                  "field": "exception.type",
                  "size": 5
                }
              },
              "avg_response_time": {
                "avg": {
                  "field": "response_time"
                }
              }
            }
          }
        }
      }

    parameters:
      - name: start_time
        type: string
        required: false
        default: "now-24h"
        description: "Start of time range"

      - name: end_time
        type: string
        required: false
        default: "now"
        description: "End of time range"

      - name: environment
        type: string
        required: false
        description: "Filter by environment"
        allowed_values: ["production", "staging", "development"]

      - name: agg_size
        type: integer
        required: false
        default: 20
        description: "Number of services to return"
        min: 1
        max: 100

    nl_examples:
      - "How many errors by service?"
      - "Show me error count per service"
      - "Which services have the most errors?"
      - "Count errors grouped by service"
      - "Break down errors by microservice"
      - "What's the error distribution across services?"

    semantic_tags:
      action: "aggregate"
      primary_entity: "application_logs"
      aggregation_type: "terms"
      group_by: "service_name"

    tags: ["logs", "aggregation", "analytics", "services"]
    result_format: "summary"

  - id: error_timeline
    version: "1.0.0"
    description: "Show error count over time with time-series visualization"
    category: "log_analytics"
    complexity: "medium"

    index: "logs-app-*"
    http_method: "POST"
    endpoint: "/{index}/_search"

    query_dsl: |
      {
        "query": {
          "bool": {
            "must": [
              {
                "match": {
                  "level": "ERROR"
                }
              }
            ],
            "filter": [
              {
                "range": {
                  "timestamp": {
                    "gte": "{{start_time}}",
                    "lte": "{{end_time}}"
                  }
                }
              }
              {% if service_name %}
              ,{
                "term": {
                  "service_name": "{{service_name}}"
                }
              }
              {% endif %}
            ]
          }
        },
        "size": 0,
        "aggs": {
          "errors_over_time": {
            "date_histogram": {
              "field": "timestamp",
              "calendar_interval": "{{interval}}",
              "min_doc_count": 0,
              "extended_bounds": {
                "min": "{{start_time}}",
                "max": "{{end_time}}"
              }
            },
            "aggs": {
              "by_level": {
                "terms": {
                  "field": "level",
                  "size": 5
                }
              }
            }
          }
        }
      }

    parameters:
      - name: start_time
        type: string
        required: false
        default: "now-24h"
        description: "Start of time range"

      - name: end_time
        type: string
        required: false
        default: "now"
        description: "End of time range"

      - name: service_name
        type: string
        required: false
        description: "Filter by specific service"

      - name: interval
        type: string
        required: false
        default: "1h"
        description: "Time bucket interval"
        allowed_values: ["1m", "5m", "15m", "30m", "1h", "6h", "12h", "1d"]

    nl_examples:
      - "Show me error trends over the last 24 hours"
      - "How have errors changed over time?"
      - "Display error timeline"
      - "Graph errors per hour"
      - "Show error count by hour"
      - "Error spike analysis for auth service"

    semantic_tags:
      action: "aggregate"
      primary_entity: "application_logs"
      aggregation_type: "date_histogram"
      time_series: true

    tags: ["logs", "analytics", "timeline", "trends"]
    result_format: "timeseries"

  - id: search_slow_requests
    version: "1.0.0"
    description: "Find slow API requests based on response time"
    category: "performance_analysis"
    complexity: "medium"

    index: "logs-app-*"
    http_method: "POST"
    endpoint: "/{index}/_search"

    query_dsl: |
      {
        "query": {
          "bool": {
            "must": [
              {
                "exists": {
                  "field": "response_time"
                }
              }
            ],
            "filter": [
              {
                "range": {
                  "timestamp": {
                    "gte": "{{start_time}}",
                    "lte": "{{end_time}}"
                  }
                }
              },
              {
                "range": {
                  "response_time": {
                    "gte": {{min_response_time}}
                  }
                }
              }
              {% if endpoint %}
              ,{
                "wildcard": {
                  "endpoint": "*{{endpoint}}*"
                }
              }
              {% endif %}
              {% if service_name %}
              ,{
                "term": {
                  "service_name": "{{service_name}}"
                }
              }
              {% endif %}
            ]
          }
        },
        "size": {{limit}},
        "sort": [
          {
            "response_time": {
              "order": "desc"
            }
          }
        ],
        "_source": ["timestamp", "service_name", "endpoint", "response_time", "status_code", "user_id", "request_id"]
      }

    parameters:
      - name: min_response_time
        type: integer
        required: false
        default: 1000
        description: "Minimum response time in milliseconds"
        min: 0

      - name: endpoint
        type: string
        required: false
        description: "API endpoint to filter"

      - name: service_name
        type: string
        required: false
        description: "Service name to filter"

      - name: start_time
        type: string
        required: false
        default: "now-1h"
        description: "Start of time range"

      - name: end_time
        type: string
        required: false
        default: "now"
        description: "End of time range"

      - name: limit
        type: integer
        required: false
        default: 50
        description: "Maximum results"
        min: 1
        max: 1000

    nl_examples:
      - "Show me slow requests"
      - "Find API calls taking more than 1 second"
      - "Which endpoints are slow?"
      - "Show requests with high response time"
      - "Find timeouts in the auth service"
      - "Display slowest API calls"

    semantic_tags:
      action: "search"
      primary_entity: "application_logs"
      qualifiers: ["slow", "performance", "timeout"]

    tags: ["performance", "slow", "requests", "monitoring"]
    result_format: "table"
```

### 1.4 Elasticsearch Adapter Configuration

**Objective**: Configure Elasticsearch adapter in ORBIT config files

**Configuration in config/adapters.yaml**:
```yaml
adapters:
  # Application Logs - Elasticsearch
  - name: "intent-elasticsearch-app-logs"
    enabled: true
    type: "retriever"
    datasource: "elasticsearch"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentElasticsearchRetriever"
    inference_provider: "openai"
    model: "gpt-4"
    embedding_provider: "openai"
    config:
      # Domain and template configuration
      domain_config_path: "utils/elasticsearch-intent-template/examples/application-logs/logs_domain.yaml"
      template_library_path:
        - "utils/elasticsearch-intent-template/examples/application-logs/logs_templates.yaml"
        - "utils/elasticsearch-intent-template/examples/application-logs/analytics_templates.yaml"

      # Vector store configuration
      template_collection_name: "elasticsearch_logs_templates"
      store_name: "chroma"

      # Intent matching configuration
      confidence_threshold: 0.4
      max_templates: 5
      return_results: 10

      # Template loading settings
      reload_templates_on_start: false
      force_reload_templates: false

      # Elasticsearch-specific configuration
      index_pattern: "logs-app-*"
      base_url: "http://localhost:9200"
      use_query_dsl: true
      enable_aggregations: true
      enable_highlighting: true
      default_size: 100

      # Authentication
      auth:
        type: "basic_auth"
        username_env: "ES_USERNAME"
        password_env: "ES_PASSWORD"

      # Fault tolerance settings
      fault_tolerance:
        operation_timeout: 30.0
        failure_threshold: 5
        recovery_timeout: 60.0
        max_retries: 3
        retry_delay: 1.0

  # System Metrics - Elasticsearch
  - name: "intent-elasticsearch-metrics"
    enabled: true
    type: "retriever"
    datasource: "elasticsearch"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentElasticsearchRetriever"
    inference_provider: "openai"
    embedding_provider: "openai"
    config:
      domain_config_path: "utils/elasticsearch-intent-template/examples/metrics/metrics_domain.yaml"
      template_library_path:
        - "utils/elasticsearch-intent-template/examples/metrics/metrics_templates.yaml"
      template_collection_name: "elasticsearch_metrics_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      index_pattern: "metrics-*"
      base_url: "http://localhost:9200"
      auth:
        type: "basic_auth"
        username_env: "ES_USERNAME"
        password_env: "ES_PASSWORD"
```

**Datasource Configuration in config/datasources.yaml**:
```yaml
datasources:
  elasticsearch:
    application_logs:
      enabled: true
      base_url: "http://localhost:9200"
      api_version: "8.x"
      use_ssl: false
      verify_certs: false
      auth:
        type: "basic_auth"
        username_env: "ES_USERNAME"
        password_env: "ES_PASSWORD"
      connection_timeout: 30
      pool_size: 10
      max_retries: 3

    metrics:
      enabled: true
      base_url: "http://localhost:9200"
      api_version: "8.x"
      use_ssl: false
      auth:
        type: "basic_auth"
        username_env: "ES_USERNAME"
        password_env: "ES_PASSWORD"

    # OpenSearch compatibility
    opensearch:
      enabled: true
      base_url: "http://localhost:9200"
      api_version: "2.x"
      compatible_mode: "opensearch"
      auth:
        type: "basic_auth"
        username_env: "OPENSEARCH_USERNAME"
        password_env: "OPENSEARCH_PASSWORD"
```

## Phase 2: Elasticsearch Template Generator Tool

**Objective**: Create comprehensive tooling for generating Elasticsearch templates from index mappings

**This phase provides automation similar to `utils/sql-intent-template/` but for Elasticsearch**

### 2.1 Elasticsearch Template Generator Directory Structure

```
utils/elasticsearch-intent-template/
├── README.md                           # Comprehensive usage guide
├── template_generator.py               # Main template generation script
├── mapping_analyzer.py                 # Analyze Elasticsearch index mappings
├── query_dsl_generator.py              # Generate Query DSL templates
├── config_selector.py                  # Auto-select config based on index type
├── validate_output.py                  # Validate generated templates
├── test_adapter_loading.py             # Test Elasticsearch adapter configuration
├── generate_templates.sh               # Shell script for template generation
├── run_example.sh                      # Quick start example script
│
├── configs/
│   ├── logs-config.yaml               # Application logs configuration
│   ├── metrics-config.yaml            # Metrics/monitoring configuration
│   ├── security-config.yaml           # Security/audit logs configuration
│   └── search-config.yaml             # Full-text search configuration
│
├── examples/
│   ├── application-logs/
│   │   ├── logs_domain.yaml           # Domain configuration
│   │   ├── logs_templates.yaml        # Generated templates
│   │   ├── analytics_templates.yaml   # Analytics templates
│   │   └── test_queries.md            # Natural language test queries
│   │
│   ├── metrics/
│   │   ├── metrics_domain.yaml
│   │   ├── metrics_templates.yaml
│   │   └── test_queries.md
│   │
│   └── security-logs/
│       ├── security_domain.yaml
│       ├── security_templates.yaml
│       └── test_queries.md
│
└── docs/
    ├── TUTORIAL.md                     # Step-by-step tutorial
    ├── QUERY_DSL_GUIDE.md             # Guide to Query DSL generation
    └── MAPPING_ANALYSIS.md             # Index mapping analysis guide
```

### 2.2 Template Generator Features

**Key Features**:
- **Index Mapping Analysis**: Automatically analyze Elasticsearch index mappings
- **Query DSL Generation**: Generate Query DSL templates from mappings and natural language queries
- **Domain Configuration**: Auto-generate domain configs from index structure
- **Natural Language Examples**: AI-powered generation of NL examples
- **Aggregation Templates**: Generate aggregation queries for analytics
- **Time-Series Support**: Specialized support for time-based data
- **Multi-Index Support**: Generate templates for multiple related indices

**Usage Example**:
```bash
# Analyze index mapping and generate domain config
python template_generator.py \
    --es-url http://localhost:9200 \
    --index "logs-app-*" \
    --generate-domain \
    --output examples/application-logs/logs_domain.yaml

# Generate templates from natural language queries
python template_generator.py \
    --es-url http://localhost:9200 \
    --index "logs-app-*" \
    --queries examples/application-logs/test_queries.md \
    --config configs/logs-config.yaml \
    --output examples/application-logs/logs_templates.yaml
```

### 2.3 Mapping Analyzer

**File**: `utils/elasticsearch-intent-template/mapping_analyzer.py`

**Capabilities**:
```python
class ElasticsearchMappingAnalyzer:
    """Analyze Elasticsearch index mappings to generate domain configurations."""

    def analyze_index(self, index_pattern: str) -> IndexAnalysis:
        """Analyze index mapping and structure."""

    def extract_searchable_fields(self, mapping: Dict) -> List[Field]:
        """Extract searchable fields from mapping."""

    def detect_time_field(self, mapping: Dict) -> Optional[str]:
        """Detect time-based field for time-series queries."""

    def suggest_aggregations(self, mapping: Dict) -> List[Aggregation]:
        """Suggest common aggregations based on field types."""

    def analyze_cardinality(self, index: str, field: str) -> int:
        """Analyze field cardinality for aggregation sizing."""
```

## Phase 3: Advanced Elasticsearch Features

### 3.1 Multi-Index Search Support

**Objective**: Support queries across multiple indices

**Features**:
- Cross-index search queries
- Index pattern matching (wildcards, comma-separated)
- Index aliasing support
- Per-index weight configuration

**Example Template**:
```yaml
# Multi-index search template
templates:
  - id: search_across_all_logs
    index: "logs-*,metrics-*"  # Multiple indices
    query_dsl: |
      {
        "query": {
          "bool": {
            "should": [
              {"match": {"message": "{{query}}"}},
              {"match": {"metric_name": "{{query}}"}}
            ]
          }
        },
        "indices_boost": [
          {"logs-*": 2.0},      # Boost log matches
          {"metrics-*": 1.0}
        ]
      }
```

### 3.2 Aggregation Pipeline Support

**Objective**: Support complex aggregation pipelines

**Features**:
- Nested aggregations
- Pipeline aggregations (derivative, moving average, etc.)
- Bucket selectors
- Aggregation scripts

**Example Template**:
```yaml
# Pipeline aggregation template
templates:
  - id: error_rate_change
    query_dsl: |
      {
        "size": 0,
        "aggs": {
          "errors_over_time": {
            "date_histogram": {
              "field": "timestamp",
              "calendar_interval": "1h"
            },
            "aggs": {
              "error_count": {
                "filter": {"term": {"level": "ERROR"}}
              },
              "error_rate_derivative": {
                "derivative": {
                  "buckets_path": "error_count._count"
                }
              }
            }
          }
        }
      }
```

### 3.3 Percolator Query Support

**Objective**: Support reverse search (percolator queries)

**Features**:
- Alert definition storage
- Real-time alert matching
- Query registration and management

### 3.4 Suggesters Support

**Objective**: Support search suggestions and autocomplete

**Features**:
- Term suggesters
- Phrase suggesters
- Completion suggesters

### 3.5 Machine Learning Integration

**Objective**: Integrate with Elasticsearch ML features

**Features**:
- Anomaly detection queries
- Data frame analytics
- Model inference

## Phase 4: Testing & Validation

### 4.1 Testing Framework

**Test Structure**:
```
tests/retrievers/implementations/intent/
├── test_intent_elasticsearch_retriever.py
├── test_elasticsearch_query_dsl_processor.py
├── test_elasticsearch_response_formatter.py
└── fixtures/
    ├── sample_mappings.json
    ├── sample_responses.json
    └── test_indices.py

utils/elasticsearch-intent-template/
├── test_template_generator.py
├── test_mapping_analyzer.py
└── test_adapter_loading.py
```

**Test Coverage**:
- Unit tests for Query DSL generation
- Integration tests with Elasticsearch test containers
- End-to-end tests with real indices
- Template validation tests
- Performance and load testing
- Aggregation accuracy tests

### 4.2 Validation Tools

**Template Validation**:
```bash
# Validate generated templates
python validate_output.py \
    --templates examples/application-logs/logs_templates.yaml \
    --domain examples/application-logs/logs_domain.yaml \
    --es-url http://localhost:9200

# Test templates against live Elasticsearch
python test_adapter_loading.py \
    --config config/adapters.yaml \
    --adapter intent-elasticsearch-app-logs \
    --test-queries "Show me errors from the last hour"
```

## Success Metrics

### Technical Metrics
- **Query Performance**: < 500ms for simple queries, < 2s for complex aggregations
- **Reliability**: 99.9% uptime for Elasticsearch adapter operations
- **Throughput**: Support 100+ concurrent queries
- **Error Rate**: < 0.5% error rate for properly configured adapters
- **Aggregation Accuracy**: 100% accurate aggregation results

### User Experience Metrics
- **Template Coverage**: 50+ pre-built templates for common log analysis patterns
- **Intent Matching Accuracy**: > 85% correct template matching
- **Query Generation Time**: < 200ms for Query DSL generation
- **Integration Time**: < 30 minutes to integrate new Elasticsearch index

### Data Metrics
- **Index Types Supported**: Logs, metrics, security events, full-text search
- **Field Types Supported**: All Elasticsearch field types (text, keyword, numeric, date, nested, etc.)
- **Aggregation Types**: Support for 20+ aggregation types
- **Time-Series Queries**: Sub-second response time for time-range queries

## Risk Mitigation

### Technical Risks

**1. Query Performance**
- **Risk**: Complex aggregations may be slow on large indices
- **Mitigation**:
  - Implement query caching
  - Use request cache and field data cache
  - Optimize index shard configuration
  - Use index lifecycle management (ILM)

**2. Index Mapping Changes**
- **Risk**: Index mapping changes may break existing templates
- **Mitigation**:
  - Version templates
  - Implement mapping validation
  - Support dynamic field mapping
  - Use field aliases for backward compatibility

**3. Elasticsearch Version Compatibility**
- **Risk**: Different Elasticsearch versions have different Query DSL syntax
- **Mitigation**:
  - Support multiple Elasticsearch versions (7.x, 8.x)
  - Version detection and adaptation
  - OpenSearch compatibility mode

**4. Memory and Resource Usage**
- **Risk**: Large result sets or aggregations may consume excessive memory
- **Mitigation**:
  - Implement scroll API for large result sets
  - Limit aggregation bucket sizes
  - Use pagination
  - Monitor circuit breakers

### Business Risks

**1. Log Volume Growth**
- **Risk**: Increasing log volume may impact query performance
- **Mitigation**:
  - Implement index rotation and retention policies
  - Use time-based indices
  - Archive old data to cold storage

**2. Cost Management**
- **Risk**: Elasticsearch cluster costs may increase with data growth
- **Mitigation**:
  - Implement data lifecycle management
  - Use tiered storage (hot/warm/cold)
  - Optimize index sizing and shard count

**3. Learning Curve**
- **Risk**: Query DSL complexity may hinder adoption
- **Mitigation**:
  - Provide comprehensive templates
  - Natural language interface reduces DSL knowledge requirement
  - Extensive documentation and examples

## Implementation Priority

### Phase 1 Priority (Weeks 1-4): Core Foundation
1. `IntentElasticsearchRetriever` class
2. Query DSL template processing
3. Basic search and filter templates
4. Domain configuration structure
5. Configuration integration

### Phase 2 Priority (Weeks 5-8): Template Generator
1. Index mapping analyzer
2. Template generator script
3. Domain config auto-generation
4. Example templates for common use cases

### Phase 3 Priority (Weeks 9-12): Advanced Features
1. Aggregation support (terms, date_histogram, metrics)
2. Multi-index search
3. Highlighting and scoring
4. Time-series optimizations

### Phase 4 Priority (Weeks 13-16): Polish & Production
1. Testing framework
2. Performance optimization
3. Documentation
4. Production deployment guide

## Compatibility Matrix

| Feature | Elasticsearch 7.x | Elasticsearch 8.x | OpenSearch 1.x | OpenSearch 2.x |
|---------|------------------|-------------------|----------------|----------------|
| Basic Search | ✅ | ✅ | ✅ | ✅ |
| Aggregations | ✅ | ✅ | ✅ | ✅ |
| Highlighting | ✅ | ✅ | ✅ | ✅ |
| Suggesters | ✅ | ✅ | ✅ | ✅ |
| Percolator | ✅ | ✅ | ✅ | ✅ |
| ML Features | ✅ | ✅ | ⚠️ Partial | ⚠️ Partial |
| Runtime Fields | ⚠️ 7.12+ | ✅ | ❌ | ⚠️ Partial |

Legend: ✅ Full Support | ⚠️ Partial Support | ❌ Not Supported

## Next Steps

1. **Review this roadmap** with the team
2. **Create Phase 1 detailed task breakdown**
3. **Set up Elasticsearch test environment**
4. **Begin `IntentElasticsearchRetriever` implementation**
5. **Create initial template examples**
6. **Test with real log data**

---

*This roadmap will be updated as implementation progresses and requirements evolve.*
