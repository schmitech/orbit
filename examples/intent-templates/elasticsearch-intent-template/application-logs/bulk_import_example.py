#!/usr/bin/env python3
#
# Manual Bulk Import Example for Elasticsearch (Python version)
#
# This script demonstrates how to manually import sample log documents
# into Elasticsearch using the Python 'requests' library.
#
# USAGE:
#   1. Ensure you have python3 and pip installed.
#   2. Install required libraries:
#      pip install requests python-dotenv
#   3. Ensure your .env file in the project root contains the Elasticsearch credentials:
#      DATASOURCE_ELASTICSEARCH_NODE=https://your-cluster.es.io:9200
#      DATASOURCE_ELASTICSEARCH_USERNAME=elastic
#      DATASOURCE_ELASTICSEARCH_PASSWORD=your-password
#
#   4. Run this script from its directory:
#      python3 bulk_import_example.py
#
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ Error: 'python-dotenv' library not found.")
    print("Please install it using: pip install python-dotenv")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("❌ Error: 'requests' library not found.")
    print("Please install it using: pip install requests")
    sys.exit(1)

def main():
    """
    Main function to run the Elasticsearch bulk import.
    """
    # Get the directory of this script to reliably locate the .env file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..', '..', '..'))
    dotenv_path = os.path.join(project_root, '.env')

    if not os.path.exists(dotenv_path):
        print(f"❌ Error: .env file not found at {dotenv_path}")
        print("Please ensure the .env file exists in the project root.")
        sys.exit(1)

    load_dotenv(dotenv_path=dotenv_path)

    # Configuration
    es_url = os.environ.get('DATASOURCE_ELASTICSEARCH_NODE', 'https://localhost:9200')
    es_username = os.environ.get('DATASOURCE_ELASTICSEARCH_USERNAME', 'elastic')
    es_password = os.environ.get('DATASOURCE_ELASTICSEARCH_PASSWORD', 'changeme')
    index_name = os.environ.get('INDEX_NAME', 'application-logs-demo')

    print("📤 Elasticsearch Bulk Import Example")
    print("======================================")
    print(f"URL: {es_url}")
    print(f"Index: {index_name}")
    print("")

    # Create index with mapping (if it doesn't exist)
    print("📋 Creating index (if needed)...")
    index_mapping = {
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
    }

    try:
        response = requests.put(
            f"{es_url}/{index_name}",
            auth=(es_username, es_password),
            json=index_mapping,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        # resource_already_exists_exception is the error type for existing index
        if response.status_code == 400 and 'resource_already_exists_exception' in response.text:
            print("   Index already exists")
        elif response.status_code != 200:
            print(f"   Error creating index: {response.status_code} {response.text}")
        else:
            print("   Index created successfully.")

    except requests.exceptions.RequestException as e:
        print(f"   Error connecting to Elasticsearch: {e}")
        sys.exit(1)


    print("")
    print("📝 Bulk importing sample documents...")

    # Bulk import using the bulk API
    bulk_data = '''
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
'''.strip().replace('"logs-app-demo"', f'"{index_name}"') + "\n"

    try:
        response = requests.post(
            f"{es_url}/_bulk",
            auth=(es_username, es_password),
            data=bulk_data.encode('utf-8'),
            headers={"Content-Type": "application/x-ndjson"},
            timeout=10
        )
        response.raise_for_status()
        print("   Bulk import successful.")
    except requests.exceptions.RequestException as e:
        print(f"   Error during bulk import: {e}")
        if e.response:
            print(f"   Response: {e.response.text}")
        sys.exit(1)


    print("")
    print("🔄 Refreshing index...")
    try:
        response = requests.post(
            f"{es_url}/{index_name}/_refresh",
            auth=(es_username, es_password),
            timeout=10
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"   Error refreshing index: {e}")
        sys.exit(1)

    print("")
    print("")
    print("✅ Import complete!")
    print("")
    print("Verify with:")
    print(f'  curl -X GET "{es_url}/{index_name}/_count" -u "{es_username}:{es_password}"')
    print("")
    print("Search example:")
    print(f'  curl -X GET "{es_url}/{index_name}/_search?q=level:ERROR" -u "{es_username}:{es_password}"')
    print("")

if __name__ == "__main__":
    main()
