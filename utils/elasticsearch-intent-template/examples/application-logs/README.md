# Application Logs - Sample Documents

This directory contains sample Elasticsearch document examples for application logs.

## Files

### Sample Documents

- **`sample_documents.json`** - Complete collection of 12 sample documents showing various log types
- **`single_error_example.json`** - Single ERROR level log with full exception details
- **`single_info_example.json`** - Single INFO level log showing successful operation

### Scripts

- **`bulk_import_example.sh`** - Shell script demonstrating manual bulk import via Elasticsearch API

### Configuration Files

- **`logs_domain.yaml`** - Domain configuration defining the application logs schema
- **`logs_templates.yaml`** - Query templates for natural language to Query DSL translation

## Document Structure

### Required Fields

All log documents include these core fields:

```json
{
  "timestamp": "2025-01-16T14:23:45.123Z",
  "level": "ERROR",
  "message": "Human-readable log message",
  "logger": "service-name.LoggerClass",
  "service_name": "service-name",
  "environment": "production",
  "host": "service-name-1.production.local",
  "request_id": "req-uuid-here"
}
```

### Optional Fields

These fields are present when applicable:

```json
{
  "user_id": "user-12345678",
  "response_time": 145,
  "status_code": 200,
  "endpoint": "/api/v1/resource"
}
```

### Exception Object (ERROR logs only)

ERROR level logs include exception details:

```json
{
  "exception": {
    "type": "TimeoutError",
    "message": "Connection timeout after 30s",
    "stacktrace": "Full stack trace..."
  }
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | date | ISO 8601 timestamp with millisecond precision |
| `level` | keyword | Log level (ERROR, WARN, INFO, DEBUG) |
| `message` | text | Human-readable log message (full-text searchable) |
| `logger` | keyword | Logger name (service.LoggerClass) |
| `service_name` | keyword | Microservice name |
| `environment` | keyword | Deployment environment (production, staging, development) |
| `host` | keyword | Server hostname |
| `request_id` | keyword | Unique request identifier for distributed tracing |
| `user_id` | keyword | User identifier (optional) |
| `response_time` | integer | Response time in milliseconds (optional) |
| `status_code` | integer | HTTP status code (optional) |
| `endpoint` | keyword | API endpoint path (optional) |
| `exception.type` | keyword | Exception class name (ERROR logs only) |
| `exception.message` | text | Exception message (ERROR logs only) |
| `exception.stacktrace` | text | Full stack trace (ERROR logs only) |

## Log Levels

### ERROR
Critical errors requiring immediate attention:
- Database connection failures
- Authentication failures
- Payment processing errors
- API timeouts
- Rate limit violations

### WARN
Warning conditions that should be monitored:
- Slow queries
- High resource usage
- Deprecated API usage
- Retry attempts
- Configuration warnings

### INFO
Informational messages about normal operations:
- Successful transactions
- User login events
- Order creation
- Job completion
- Configuration reloads

### DEBUG
Detailed information for debugging:
- Function entry/exit
- Cache hits/misses
- Query parameters
- Data validation
- Internal state

## Services

The sample data includes logs from these microservices:

- **auth-service** - Authentication and authorization
- **user-service** - User management
- **order-service** - Order processing
- **payment-service** - Payment processing
- **inventory-service** - Inventory management
- **notification-service** - Notification delivery
- **api-gateway** - API gateway and routing
- **data-pipeline** - Data processing and ETL
- **search-service** - Search functionality
- **recommendation-service** - Recommendation engine
- **analytics-service** - Analytics and reporting

## Quick Import

### Using the Sample Data Generator (Recommended)

```bash
# Generate 1000 realistic logs
python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count 1000 \
    --index logs-app-demo
```

### Manual Import with curl

```bash
# Set credentials
export ES_URL="https://your-cluster.es.io:9200"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"

# Run bulk import
./bulk_import_example.sh
```

### Single Document Import

```bash
# Import one document
curl -X POST "$ES_URL/logs-app-demo/_doc" \
  -u "$ES_USERNAME:$ES_PASSWORD" \
  -H "Content-Type: application/json" \
  -d @single_error_example.json
```

## Example Queries

After importing data, test these natural language queries:

### Error Analysis
```
"Show me recent error logs"
"Find errors from the last hour"
"What errors did user-12345678 encounter?"
"Show me errors in the payment service"
```

### Performance Analysis
```
"Find slow API requests"
"Show me requests taking more than 2 seconds"
"Which endpoints are slow?"
```

### Service Analysis
```
"How many errors by service?"
"Which services have the most errors?"
"Show error count per service"
```

### User Activity
```
"Show me logs for user-12345678"
"What did user-87654321 do?"
"Find activity for user-11223344"
```

### Time-Based Analysis
```
"Show me error trends over the last 24 hours"
"Display error timeline"
"How have errors changed over time?"
```

## Elasticsearch Query DSL Examples

### Find Error Logs
```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"level": "ERROR"}}
      ],
      "filter": [
        {
          "range": {
            "timestamp": {
              "gte": "now-1h",
              "lte": "now"
            }
          }
        }
      ]
    }
  }
}
```

### Aggregate Errors by Service
```json
{
  "size": 0,
  "aggs": {
    "by_service": {
      "terms": {
        "field": "service_name",
        "size": 10
      }
    }
  }
}
```

### Find Slow Requests
```json
{
  "query": {
    "range": {
      "response_time": {
        "gte": 2000
      }
    }
  },
  "sort": [
    {"response_time": {"order": "desc"}}
  ]
}
```

## Index Mapping

The logs use this Elasticsearch mapping:

```json
{
  "properties": {
    "timestamp": {"type": "date"},
    "level": {"type": "keyword"},
    "message": {"type": "text", "analyzer": "standard"},
    "logger": {"type": "keyword"},
    "service_name": {"type": "keyword"},
    "environment": {"type": "keyword"},
    "host": {"type": "keyword"},
    "request_id": {"type": "keyword"},
    "user_id": {"type": "keyword"},
    "response_time": {"type": "integer"},
    "status_code": {"type": "integer"},
    "endpoint": {"type": "keyword"},
    "exception": {
      "properties": {
        "type": {"type": "keyword"},
        "message": {"type": "text"},
        "stacktrace": {"type": "text"}
      }
    }
  }
}
```

## Best Practices

### Indexing
- Use bulk API for importing multiple documents
- Set appropriate refresh intervals for your use case
- Consider using index templates for automatic mapping
- Use index lifecycle management for log retention

### Querying
- Use keyword fields for exact matching and aggregations
- Use text fields for full-text search
- Filter on date ranges for better performance
- Use aggregations for analytics and summaries

### Performance
- Set `number_of_replicas: 0` for initial data loading
- Increase after data is loaded for high availability
- Use appropriate shard sizing based on data volume
- Monitor index size and query performance

## Next Steps

1. **Generate Sample Data**: Use the sample data generator for realistic test data
2. **Enable Adapter**: Set `enabled: true` in `config/adapters.yaml`
3. **Test Queries**: Try natural language queries through ORBIT
4. **Create Templates**: Add custom query templates for your use cases
5. **Monitor Performance**: Watch query performance and optimize as needed

## Related Documentation

- [Sample Data Generator Guide](../../SAMPLE_DATA.md)
- [Domain Configuration](logs_domain.yaml)
- [Query Templates](logs_templates.yaml)
- [Main README](../../README.md)
