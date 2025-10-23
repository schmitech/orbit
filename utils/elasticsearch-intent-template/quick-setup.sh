#!/bin/bash
#
# Quick Setup Script for Elasticsearch Intent Adapter
#
# This script helps you quickly set up and test the Elasticsearch intent adapter
# with sample data.
#

set -e  # Exit on error

echo "🚀 Elasticsearch Intent Adapter - Quick Setup"
echo "================================================"
echo ""

# Check if credentials are set
if [ -z "$DATASOURCE_ELASTICSEARCH_USERNAME" ] || [ -z "$DATASOURCE_ELASTICSEARCH_PASSWORD" ]; then
    echo "⚠️  Elasticsearch credentials not found in environment"
    echo ""
    echo "Please set your credentials:"
    echo "  export DATASOURCE_ELASTICSEARCH_USERNAME=elastic"
    echo "  export DATASOURCE_ELASTICSEARCH_PASSWORD=your-password"
    echo ""
    read -p "Do you want to enter them now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Username: " ES_USERNAME
        read -s -p "Password: " ES_PASSWORD
        echo ""
        export DATASOURCE_ELASTICSEARCH_USERNAME=$ES_USERNAME
        export DATASOURCE_ELASTICSEARCH_PASSWORD=$ES_PASSWORD
        echo "✅ Credentials set for this session"
    else
        echo "❌ Cannot proceed without credentials"
        exit 1
    fi
fi

# Check if Python dependencies are installed
echo ""
echo "📦 Checking dependencies..."
if ! python -c "import faker" 2>/dev/null; then
    echo "⚠️  Faker not installed"
    read -p "Install Faker? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install faker
        echo "✅ Faker installed"
    else
        echo "❌ Faker is required"
        exit 1
    fi
else
    echo "✅ Faker is installed"
fi

# Ask for setup options
echo ""
echo "📊 Setup Options"
echo "================================================"

# Number of records
read -p "Number of log records to generate (default: 1000): " RECORD_COUNT
RECORD_COUNT=${RECORD_COUNT:-1000}

# Index name
read -p "Index name (default: logs-app-demo): " INDEX_NAME
INDEX_NAME=${INDEX_NAME:-logs-app-demo}

# Use AI or not
echo ""
read -p "Use AI for realistic messages? (slower but better quality) (y/n) " -n 1 -r
echo
USE_AI=""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    USE_AI="--use-ai"
    read -p "AI Provider (openai/anthropic/cohere, default: openai): " AI_PROVIDER
    AI_PROVIDER=${AI_PROVIDER:-openai}
    USE_AI="$USE_AI --provider $AI_PROVIDER"
    echo "✅ Will use AI with $AI_PROVIDER"
else
    echo "✅ Will use template-based generation (faster)"
fi

# Confirm
echo ""
echo "📋 Configuration Summary"
echo "================================================"
echo "Records:     $RECORD_COUNT"
echo "Index:       $INDEX_NAME"
if [ -n "$USE_AI" ]; then
    echo "AI:          Enabled ($AI_PROVIDER)"
else
    echo "AI:          Disabled (template-based)"
fi
echo ""
read -p "Proceed with generation? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 1
fi

# Generate data
echo ""
echo "🔄 Generating sample data..."
echo "================================================"

cd "$(dirname "$0")/../.."

python utils/elasticsearch-intent-template/generate_sample_data.py \
    --count $RECORD_COUNT \
    --index $INDEX_NAME \
    $USE_AI

# Validate
echo ""
echo "✅ Data generation complete!"
echo ""
read -p "Validate the indexed data? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    python utils/elasticsearch-intent-template/validate_data.py --index $INDEX_NAME
fi

# Next steps
echo ""
echo "🎉 Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Enable the adapter in config/adapters.yaml:"
echo "   - name: \"intent-elasticsearch-app-logs\""
echo "     enabled: true"
echo ""
echo "2. Update the index pattern if needed:"
echo "   config:"
echo "     index_pattern: \"$INDEX_NAME\""
echo ""
echo "3. Start the ORBIT server and test queries:"
echo "   - \"Show me recent error logs\""
echo "   - \"How many errors by service?\""
echo "   - \"Find slow API requests\""
echo ""
echo "See utils/elasticsearch-intent-template/README.md for more examples!"
echo ""
