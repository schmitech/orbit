# Elasticsearch Dev Tools — Sample Queries

Paste these into **Kibana → Dev Tools** (or Elastic Cloud Dev Tools).
The default index is `application-logs-demo`. Replace it if you used `--index` when generating data.

---

## 1. Index & Cluster Health

### Check the index exists and get document count
```
GET application-logs-demo/_count
```

### View the index mapping
```
GET application-logs-demo/_mapping
```

### Index stats (size, shard info)
```
GET application-logs-demo/_stats
```

---

## 2. Basic Search (GET /_search)

### Return the 10 most recent log entries
```
GET application-logs-demo/_search
{
  "size": 10,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "level", "service_name", "message"]
}
```

### Search across all fields for a keyword
```
GET application-logs-demo/_search
{
  "query": {
    "multi_match": {
      "query": "timeout",
      "fields": ["message", "exception.message", "exception.stacktrace"]
    }
  },
  "size": 10,
  "_source": ["timestamp", "level", "service_name", "message"]
}
```

### Filter by log level (exact keyword match)
```
GET application-logs-demo/_search
{
  "query": {
    "term": { "level": "ERROR" }
  },
  "size": 20,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "level", "service_name", "message", "exception.type"]
}
```

### Filter by service name
```
GET application-logs-demo/_search
{
  "query": {
    "term": { "service_name.keyword": "payment-service" }
  },
  "size": 20,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "level", "message", "response_time", "status_code"]
}
```

### Full-text search in messages with fuzzy matching
```
GET application-logs-demo/_search
{
  "query": {
    "match": {
      "message": {
        "query": "database connection failed",
        "operator": "AND",
        "fuzziness": "AUTO"
      }
    }
  },
  "highlight": {
    "fields": { "message": {} }
  },
  "size": 10
}
```

### Trace a specific request across all services
```
GET application-logs-demo/_search
{
  "query": {
    "term": { "request_id": "REPLACE_WITH_ACTUAL_REQUEST_ID" }
  },
  "sort": [{ "timestamp": { "order": "asc" } }],
  "_source": ["timestamp", "service_name", "level", "message", "response_time"]
}
```

---

## 3. Range Queries

### Logs from the last 24 hours
```
GET application-logs-demo/_search
{
  "query": {
    "range": {
      "timestamp": {
        "gte": "now-24h",
        "lte": "now"
      }
    }
  },
  "size": 20,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "level", "service_name", "message"]
}
```

### Logs between two specific dates
```
GET application-logs-demo/_search
{
  "query": {
    "range": {
      "timestamp": {
        "gte": "2025-01-15T00:00:00Z",
        "lte": "2025-01-16T23:59:59Z",
        "format": "strict_date_time"
      }
    }
  },
  "size": 50,
  "sort": [{ "timestamp": { "order": "desc" } }]
}
```

### Slow requests — response time over 2000ms
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "range": { "response_time": { "gte": 2000 } } },
        { "range": { "timestamp": { "gte": "now-7d" } } }
      ]
    }
  },
  "sort": [{ "response_time": { "order": "desc" } }],
  "size": 20,
  "_source": ["timestamp", "service_name", "endpoint", "response_time", "status_code"]
}
```

### HTTP 5xx errors in the last week
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "range": { "status_code": { "gte": 500, "lt": 600 } } },
        { "range": { "timestamp": { "gte": "now-7d" } } }
      ]
    }
  },
  "size": 20,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "service_name", "endpoint", "status_code", "message"]
}
```

### HTTP 4xx client errors (range on status code)
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "range": { "status_code": { "gte": 400, "lt": 500 } } },
        { "range": { "timestamp": { "gte": "now-24h" } } }
      ]
    }
  },
  "size": 20,
  "sort": [{ "timestamp": { "order": "desc" } }],
  "_source": ["timestamp", "service_name", "endpoint", "status_code", "user_id"]
}
```

### Combined: errors in a time window with slow response
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "level": "ERROR" } },
        { "range": { "timestamp": { "gte": "now-6h" } } },
        { "range": { "response_time": { "gte": 5000 } } }
      ]
    }
  },
  "size": 20,
  "sort": [{ "response_time": { "order": "desc" } }],
  "_source": ["timestamp", "service_name", "endpoint", "response_time", "exception.type", "message"]
}
```

---

## 4. Aggregations

### Error count grouped by service (last 24h)
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "level": "ERROR" } },
        { "range": { "timestamp": { "gte": "now-24h" } } }
      ]
    }
  },
  "size": 0,
  "aggs": {
    "errors_by_service": {
      "terms": { "field": "service_name.keyword", "size": 20 }
    }
  }
}
```

### Average response time per endpoint
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "exists": { "field": "response_time" } },
        { "range": { "timestamp": { "gte": "now-24h" } } }
      ]
    }
  },
  "size": 0,
  "aggs": {
    "by_endpoint": {
      "terms": { "field": "endpoint", "size": 20 },
      "aggs": {
        "avg_rt": { "avg": { "field": "response_time" } },
        "p95_rt": { "percentiles": { "field": "response_time", "percents": [95] } }
      }
    }
  }
}
```

### Error timeline — errors per hour over the last 7 days
```
GET application-logs-demo/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "level": "ERROR" } },
        { "range": { "timestamp": { "gte": "now-7d" } } }
      ]
    }
  },
  "size": 0,
  "aggs": {
    "errors_over_time": {
      "date_histogram": {
        "field": "timestamp",
        "fixed_interval": "1h",
        "min_doc_count": 0,
        "extended_bounds": { "min": "now-7d", "max": "now" }
      }
    }
  }
}
```

---

## 5. Delete by Query

> **Warning:** these permanently remove documents. Run the matching `GET` first to confirm scope.

### Delete all DEBUG logs older than 30 days
```
POST application-logs-demo/_delete_by_query
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "level": "DEBUG" } },
        { "range": { "timestamp": { "lt": "now-30d" } } }
      ]
    }
  }
}
```

### Delete logs for a specific environment
```
POST application-logs-demo/_delete_by_query
{
  "query": {
    "term": { "environment": "staging" }
  }
}
```

### Delete all logs from a specific date range (bulk cleanup)
```
POST application-logs-demo/_delete_by_query
{
  "query": {
    "range": {
      "timestamp": {
        "gte": "2025-01-01T00:00:00Z",
        "lte": "2025-01-14T23:59:59Z"
      }
    }
  }
}
```

### Delete a specific request trace (all logs sharing a request_id)
```
POST application-logs-demo/_delete_by_query
{
  "query": {
    "term": { "request_id": "REPLACE_WITH_ACTUAL_REQUEST_ID" }
  }
}
```

### Delete all documents (wipe index contents, keep mapping)
```
POST application-logs-demo/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}
```

---

## 6. Index Management

### Refresh the index (make newly indexed docs searchable immediately)
```
POST application-logs-demo/_refresh
```

### Force merge (reduce segment count after bulk deletes)
```
POST application-logs-demo/_forcemerge?max_num_segments=1
```

### Delete the entire index
```
DELETE application-logs-demo
```
