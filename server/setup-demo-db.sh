#!/bin/bash

set -e

# Check if datasource argument is provided
if [ "$1" != "sqlite" ] && [ "$1" != "chroma" ]; then
    echo "Usage: $0 [sqlite|chroma]"
    echo "Please specify the datasource type: sqlite or chroma"
    exit 1
fi

DATASOURCE=$1

# Find config.yaml (same logic as start.sh)
CONFIG_PATH="config.yaml"
if [ ! -f "$CONFIG_PATH" ]; then
    CONFIG_PATH="../config/config.yaml"
fi
if [ ! -f "$CONFIG_PATH" ]; then
    CONFIG_PATH="../../config/config.yaml"
fi

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Warning: Config file not found. Defaulting to port 3000."
    PORT="3000"
else
    # Determine if HTTPS is enabled
    HTTPS_ENABLED=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('enabled', False))
")
    if [ "$HTTPS_ENABLED" = "True" ]; then
        PORT=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('port', 3443))
")
    else
        PORT=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('port', 3000))
")
    fi
fi

echo "🚀 Setting up sample QA collections..."

if [ "$DATASOURCE" = "sqlite" ]; then
    # Remove existing SQLite database directory if it exists
    if [ -d "./sqlite_db" ]; then
        echo "Removing existing SQLite database..."
        rm -rf ./sqlite_db
    fi

    # Create new SQLite database with sample data
    python ../utils/sqllite/rag_cli.py setup --db-path ./sqlite_db --data-path ../utils/sample-data/city-qa-pairs.json
else
    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null; then
        echo "Error: Ollama is not running. Please start Ollama before proceeding."
        exit 1
    fi

    # Check if nomic-embed-text model exists
    if ! curl -s http://localhost:11434/api/tags | grep -q "nomic-embed-text"; then
        echo "Error: nomic-embed-text model not found in Ollama."
        echo "Please pull the model using: ollama pull nomic-embed-text"
        exit 1
    fi

    # Remove existing Chroma database directory if it exists
    if [ -d "./chroma_db" ]; then
        echo "Removing existing Chroma database..."
        rm -rf ./chroma_db
    fi

    # Create Chroma collections
    echo "Creating Chroma collections..."
    python ../utils/chroma/scripts/create_qa_pairs_collection.py city ../utils/sample-data/city-qa-pairs.json --local --db-path ./chroma_db
    python ../utils/chroma/scripts/create_qa_pairs_collection.py activity ../utils/sample-data/activity_qa_pairs.json --local --db-path ./chroma_db
fi

echo "✅ Sample QA collections created."
echo ""
echo "🔑 Creating API keys for collections..."
echo "  • Connecting to server on port $PORT"
echo "  • Using collection 'city'"
echo "  • Using prompt file '../prompts/examples/city/city-assistant-normal-prompt.txt'"
echo ""

# Create API key for 'city' collection and capture full output
API_KEY_OUTPUT=$(python3 ./admin/api_key_manager.py --url http://localhost:$PORT create \
  --collection city \
  --name "City Assistant" \
  --prompt-file ../prompts/examples/city/city-assistant-normal-prompt.txt \
  --prompt-name "Municipal Assistant Prompt")

# Extract just the API key - properly capture orbit_ format keys
CITY_API_KEY=$(echo "$API_KEY_OUTPUT" | grep -o '"api_key": "orbit_[A-Za-z0-9]\+"' | cut -d'"' -f4)

echo "✅ API key created successfully!"

# If using Chroma, create additional API key for activity collection
if [ "$DATASOURCE" = "chroma" ]; then
    echo ""
    echo "🔑 Creating API key for activity collection..."
    echo "  • Using collection 'activity'"
    echo "  • Using prompt file '../prompts/examples/activity/activity-assistant-normal-prompt.txt'"
    echo ""

    ACTIVITY_API_KEY_OUTPUT=$(python3 ./admin/api_key_manager.py --url http://localhost:$PORT create \
      --collection activity \
      --name "Activity Assistant" \
      --prompt-file ../prompts/examples/activity/activity-assistant-normal-prompt.txt \
      --prompt-name "Activity Assistant Prompt")

    ACTIVITY_API_KEY=$(echo "$ACTIVITY_API_KEY_OUTPUT" | grep -o '"api_key": "orbit_[A-Za-z0-9]\+"' | cut -d'"' -f4)
    echo "✅ Activity API key created successfully!"
fi

echo ""
echo "🎉 Demo database setup complete!"
echo ""
echo "You can now test the server using the Python client."
echo ""
echo "================================================================"
echo "CLIENT SETUP INSTRUCTIONS:"
echo "================================================================"
echo ""
echo "Run these commands to set up and start the client:"
echo ""
echo "  cd ../clients/python"
echo "  python -m venv venv"
echo "  source venv/bin/activate"
echo "  pip install -r requirements.txt"
echo ""
echo "Then run this command to chat with your ORBIT assistant:"
echo ""
echo "  python chat_client.py --url http://localhost:$PORT --api-key $CITY_API_KEY"
echo ""
echo "================================================================"
echo "API KEYS:"
echo "================================================================"
echo "City API KEY: $CITY_API_KEY"
if [ "$DATASOURCE" = "chroma" ]; then
    echo ""
    echo "Activity API KEY: $ACTIVITY_API_KEY"
fi
echo "================================================================"
echo ""
echo "Happy orbiting! 🚀"
