#!/bin/bash
#
# Manual Bulk Import Example for Elasticsearch
#
# This script demonstrates how to manually import sample log documents
# into Elasticsearch using the bulk API.
#
# USAGE:
#   1. Set your Elasticsearch credentials:
#      export ES_URL="https://your-cluster.es.io:9200"
#      export ES_USERNAME="elastic"
#      export ES_PASSWORD="your-password"
#
#   2. Run this script:
#      ./bulk_import_example.sh
#

set -e

# Configuration
ES_URL="${ES_URL:-https://localhost:9200}"
ES_USERNAME="${ES_USERNAME:-elastic}"
ES_PASSWORD="${ES_PASSWORD:-changeme}"
INDEX_NAME="${INDEX_NAME:-logs-app-demo}"

echo "📤 Elasticsearch Bulk Import Example"
echo "======================================"
echo "URL: $ES_URL"
echo "Index: $INDEX_NAME"
echo ""

# Create index with mapping (if it doesn't exist)
echo "📋 Creating index (if needed)..."
curl -X PUT "$ES_URL/$INDEX_NAME" \
  -u "$ES_USERNAME:$ES_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  },
  "mappings": {
    "properties": {
      "timestamp": {"type": "date"},
      "level": {"type": "keyword"},
      "message": {"type": "text"},
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
}' 2>/dev/null || echo "   Index already exists"

echo ""
echo "📝 Bulk importing sample documents..."

# Bulk import using the bulk API
# Format: {index metadata}\n{document}\n{index metadata}\n{document}\n...
curl -X POST "$ES_URL/_bulk" \
  -u "$ES_USERNAME:$ES_PASSWORD" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @- << 'EOF'
{"index":{"_index":"logs-app-demo"}}
{"timestamp":"2025-01-16T14:23:45.123Z","level":"ERROR","message":"Failed to process payment: Database connection timeout","logger":"payment-service.TransactionLogger","service_name":"payment-service","environment":"production","host":"payment-service-3.production.local","request_id":"req-001","user_id":"user-12345678","response_time":30500,"status_code":500,"endpoint":"/api/v1/payments","exception":{"type":"TimeoutError","message":"Connection timeout after 30s","stacktrace":"File payment-service/transaction.py, line 145"}}
{"index":{"_index":"logs-app-demo"}}
{"timestamp":"2025-01-16T14:24:12.456Z","level":"WARN","message":"Slow query detected: took 2547ms","logger":"order-service.QueryLogger","service_name":"order-service","environment":"production","host":"order-service-7.production.local","request_id":"req-002","user_id":"user-12345678","response_time":2547,"status_code":200,"endpoint":"/api/v1/orders"}
{"index":{"_index":"logs-app-demo"}}
{"timestamp":"2025-01-16T14:24:18.789Z","level":"INFO","message":"Order ORD-abc12345 created successfully","logger":"order-service.OrderLogger","service_name":"order-service","environment":"production","host":"order-service-7.production.local","request_id":"req-003","user_id":"user-87654321","response_time":145,"status_code":201,"endpoint":"/api/v1/orders"}
{"index":{"_index":"logs-app-demo"}}
{"timestamp":"2025-01-16T14:25:03.234Z","level":"ERROR","message":"Authentication failed for user","logger":"auth-service.AuthLogger","service_name":"auth-service","environment":"production","host":"auth-service-2.production.local","request_id":"req-004","user_id":"user-99887766","response_time":523,"status_code":401,"endpoint":"/api/v1/auth/login","exception":{"type":"AuthenticationError","message":"Invalid credentials","stacktrace":"File auth-service/authentication.py, line 78"}}
{"index":{"_index":"logs-app-demo"}}
{"timestamp":"2025-01-16T14:25:15.567Z","level":"INFO","message":"User logged in from 192.168.1.100","logger":"auth-service.SessionLogger","service_name":"auth-service","environment":"production","host":"auth-service-1.production.local","request_id":"req-005","user_id":"user-11223344","response_time":87,"status_code":200,"endpoint":"/api/v1/auth/login"}
EOF

echo ""
echo "🔄 Refreshing index..."
curl -X POST "$ES_URL/$INDEX_NAME/_refresh" \
  -u "$ES_USERNAME:$ES_PASSWORD"

echo ""
echo ""
echo "✅ Import complete!"
echo ""
echo "Verify with:"
echo "  curl -X GET \"$ES_URL/$INDEX_NAME/_count\" -u \"$ES_USERNAME:$ES_PASSWORD\""
echo ""
echo "Search example:"
echo "  curl -X GET \"$ES_URL/$INDEX_NAME/_search?q=level:ERROR\" -u \"$ES_USERNAME:$ES_PASSWORD\""
echo ""
