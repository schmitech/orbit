#!/bin/bash

# Demo Data Generation Script
# This script runs the Elasticsearch sample data generator with optimized settings
# for a high-quality demonstration.

# 1. Configuration (adjust if needed)
COUNT=10000
DAYS_BACK=30
ERROR_RATE=25
INDEX_NAME="application-logs-demo"
SEED=12345

# 2. Check for Elasticsearch credentials
if [ -z "$DATASOURCE_ELASTICSEARCH_USERNAME" ] || [ -z "$DATASOURCE_ELASTICSEARCH_PASSWORD" ]; then
    echo "⚠️  Warning: DATASOURCE_ELASTICSEARCH_USERNAME or DATASOURCE_ELASTICSEARCH_PASSWORD not set."
    echo "Please set them or ensure they are in your .env file."
fi

# 3. Execute the generator
echo "🚀 Starting demo data generation ($COUNT records, $DAYS_BACK days)..."

python3 "$(dirname "$0")/generate_sample_data.py" \
    --count $COUNT \
    --days-back $DAYS_BACK \
    --error-rate $ERROR_RATE \
    --index "$INDEX_NAME" \
    --seed $SEED

echo "✅ Generation complete. Index: $INDEX_NAME"
