#!/bin/bash

# sample-db-setup.sh
# This script sets up a sample database for the ORBIT system with either SQLite or Chroma as the backend.
#
# Usage:
#   ./sample-db-setup.sh [--no-api-keys] [sqlite|chroma]
#   ./sample-db-setup.sh [--no-api-keys] [--sqlite|--chroma]
#
# Options:
#   --no-api-keys    Skip API key creation
#   sqlite|chroma    Specify the datasource type
#   --sqlite         Specify SQLite as the datasource type
#   --chroma         Specify Chroma as the datasource type
#
# Examples:
#   ./sample-db-setup.sh sqlite              # Set up SQLite database with API keys
#   ./sample-db-setup.sh --sqlite            # Set up SQLite database with API keys
#   ./sample-db-setup.sh chroma              # Set up Chroma database with API keys
#   ./sample-db-setup.sh --chroma            # Set up Chroma database with API keys
#   ./sample-db-setup.sh --no-api-keys sqlite # Set up SQLite database without API keys
#
# The script will:
# 1. Set up the specified database type (SQLite or Chroma)
# 2. Create sample QA collections
# 3. Optionally create API keys for the adapters (uses new adapter-based approach)
# 4. Display setup instructions and API keys if created

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the project root (parent of install directory)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default value for CREATE_API_KEYS
CREATE_API_KEYS=true
DATASOURCE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-api-keys)
            CREATE_API_KEYS=false
            shift
            ;;
        --sqlite)
            DATASOURCE="sqlite"
            shift
            ;;
        --chroma)
            DATASOURCE="chroma"
            shift
            ;;
        sqlite|chroma)
            DATASOURCE=$1
            shift
            ;;
        *)
            echo "Usage: $0 [--no-api-keys] [sqlite|chroma]"
            echo "       $0 [--no-api-keys] [--sqlite|--chroma]"
            echo "Options:"
            echo "  --no-api-keys    Skip API key creation"
            echo "  sqlite|chroma    Specify the datasource type"
            echo "  --sqlite         Specify SQLite as the datasource type"
            echo "  --chroma         Specify Chroma as the datasource type"
            exit 1
            ;;
    esac
done

# Check if datasource argument is provided
if [ -z "$DATASOURCE" ]; then
    echo "Usage: $0 [--no-api-keys] [sqlite|chroma]"
    echo "       $0 [--no-api-keys] [--sqlite|--chroma]"
    echo "Please specify the datasource type: sqlite, chroma, --sqlite, or --chroma"
    exit 1
fi

# Find config.yaml with absolute paths
CONFIG_PATH="$PROJECT_ROOT/config.yaml"
if [ ! -f "$CONFIG_PATH" ]; then
    CONFIG_PATH="$PROJECT_ROOT/config/config.yaml"
fi

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Warning: Config file not found. Defaulting to port 3000."
    PORT="3000"
    USE_LOCAL="true"  # Default to local if config not found
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
        PROTOCOL="https"
    else
        PORT=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('port', 3000))
")
        PROTOCOL="http"
    fi
    
    # Read use_local setting from config
    USE_LOCAL=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(str(config.get('datasources', {}).get('chroma', {}).get('use_local', True)).lower())
")
fi

# Set default protocol if not set
if [ -z "$PROTOCOL" ]; then
    PROTOCOL="http"
fi

echo "🚀 Setting up sample QA collections..."

if [ "$DATASOURCE" = "sqlite" ]; then
    # Remove existing SQLite database directory if it exists
    if [ -d "$PROJECT_ROOT/sqlite_db" ]; then
        echo "Removing existing SQLite database..."
        rm -rf "$PROJECT_ROOT/sqlite_db"
    fi

    # Create new SQLite database with sample data
    python3 "$PROJECT_ROOT/examples/sqlite/rag_cli.py" setup --db-path "$PROJECT_ROOT/examples/sqlite/sqlite_db" --data-path "$PROJECT_ROOT/examples/city-qa-pairs.json"
else
    # Remove existing Chroma database directory if it exists
    if [ "$USE_LOCAL" = "true" ]; then
        if [ -d "$PROJECT_ROOT/chroma_db" ]; then
            echo "Removing existing Chroma database..."
            rm -rf "$PROJECT_ROOT/chroma_db"
        fi
    fi

    # Create Chroma collections
    echo "Creating Chroma collections..."
    LOCAL_FLAG=""
    if [ "$USE_LOCAL" = "true" ]; then
        LOCAL_FLAG="--local --db-path $PROJECT_ROOT/examples/chroma/chroma_db"
    fi
    
    # Load Q&A pairs
    python3 "$PROJECT_ROOT/examples/chroma/create_qa_pairs_collection.py" city "$PROJECT_ROOT/examples/city-qa-pairs.json" $LOCAL_FLAG
    
    # Uncomment to create sample activity collection (will take lonnger due to volume of data)
    # python3 "$PROJECT_ROOT/examples/chroma/create_qa_pairs_collection.py" activity "$PROJECT_ROOT/examples/activity-qa-pairs.json" $LOCAL_FLAG
fi

echo "✅ Sample QA collections created."

if [ "$CREATE_API_KEYS" = true ]; then
    echo ""
    echo "🔑 Creating API keys using new adapter-based approach..."
    
    # Determine which adapter to use based on datasource
    if [ "$DATASOURCE" = "sqlite" ]; then
        ADAPTER_NAME="qa-sql"
        echo "  • Using adapter '$ADAPTER_NAME' for SQLite Q&A data"
    else
        ADAPTER_NAME="qa-vector-chroma"
        echo "  • Using adapter '$ADAPTER_NAME' for Chroma Q&A data"
    fi
    
    echo "  • Connecting to server on port $PORT"
    echo "  • Using prompt file '$PROJECT_ROOT/examples/prompts/examples/city/city-assistant-normal-prompt.txt'"
    echo ""

    # Create API key using new adapter-based approach
    SERVER_URL="${PROTOCOL}://localhost:${PORT}"
    echo "Debug: Connecting to server at $SERVER_URL"
    
    # Check if server is running before attempting to create API keys
    echo "Checking if server is running..."
    
    # Function to check if server is responding
    check_server_health() {
        local max_attempts=12  # Try for up to 60 seconds (12 * 5 seconds)
        local attempt=1
        
        while [ $attempt -le $max_attempts ]; do
            echo "Attempt $attempt/$max_attempts: Checking server health..."
            
            # Try the health endpoint first (preferred)
            if curl -s --connect-timeout 10 --max-time 15 "${SERVER_URL}/health" > /dev/null 2>&1; then
                echo "✅ Server health endpoint responded successfully"
                return 0
            fi
            
            # If health endpoint fails, try a simpler endpoint
            if curl -s --connect-timeout 5 --max-time 10 "${SERVER_URL}/favicon.ico" > /dev/null 2>&1; then
                echo "✅ Server is responding (favicon endpoint)"
                return 0
            fi
            
            # If both fail, wait and try again
            if [ $attempt -lt $max_attempts ]; then
                echo "Server not ready yet, waiting 5 seconds... ($attempt/$max_attempts)"
                sleep 5
            fi
            
            attempt=$((attempt + 1))
        done
        
        return 1
    }
    
    if ! check_server_health; then
        echo "❌ Error: Server is not responding at ${SERVER_URL}"
        echo "The server may still be starting up or there may be an issue."
        echo ""
        echo "Please check:"
        echo "  1. Server is running: python $PROJECT_ROOT/bin/orbit.py start"
        echo "  2. Server logs for any startup errors: tail -f $PROJECT_ROOT/logs/orbit.log"
        echo "  3. Server is accessible at: ${SERVER_URL}"
        echo ""
        echo "Once the server is fully started, run this script again."
        exit 1
    fi
    
    # Check if we need to authenticate first
    echo "Checking authentication status..."
    AUTH_STATUS=$(python3 "$PROJECT_ROOT/bin/orbit.py" auth-status 2>/dev/null || echo 'not authenticated')
    
    if echo "$AUTH_STATUS" | grep -q 'authenticated'; then
        echo "✅ Authentication verified"
    else
        echo "❌ Not authenticated. Please login first:"
        echo "  python $PROJECT_ROOT/bin/orbit.py login"
        echo "Then run this script again."
        exit 1
    fi
    
    # Create API key using new --adapter flag instead of deprecated --collection flag
    API_KEY_OUTPUT=$(python3 "$PROJECT_ROOT/bin/orbit.py" key create \
      --adapter "$ADAPTER_NAME" \
      --name "City Assistant" \
      --notes "This is a sample API key for the City Assistant using adapter '$ADAPTER_NAME'." \
      --prompt-file "$PROJECT_ROOT/examples/prompts/examples/city/city-assistant-normal-prompt.txt" \
      --prompt-name "Municipal Assistant Prompt")

    # Extract just the API key - properly capture orbit_ format keys
    CITY_API_KEY=$(echo "$API_KEY_OUTPUT" | grep -o 'orbit_[A-Za-z0-9]\+' | head -1)

    echo "✅ API key created successfully using adapter approach!"

    # If using Chroma, create additional API key for activity collection
    if [ "$DATASOURCE" = "chroma" ]; then
        echo ""
        echo "🔑 Creating API key for activity collection..."
        echo "  • Using adapter 'qa-vector-chroma' for activity data"
        echo "  • Using prompt file '$PROJECT_ROOT/examples/prompts/examples/activity/activity-assistant-normal-prompt.txt'"
        echo ""

        # Uncomment to generate an API Key for the activity collection using new adapter approach
        # ACTIVITY_API_KEY_OUTPUT=$(python3 "$PROJECT_ROOT/bin/orbit.py" key create \
        #   --adapter qa-vector-chroma \
        #   --name "Activity Assistant" \
        #   --notes "This is a sample API key for the Activity Assistant using adapter 'qa-vector-chroma'." \
        #   --prompt-file "$PROJECT_ROOT/examples/prompts/examples/activity/activity-assistant-normal-prompt.txt" \
        #   --prompt-name "Activity Assistant Prompt")

        # ACTIVITY_API_KEY=$(echo "$ACTIVITY_API_KEY_OUTPUT" | grep -o 'orbit_[A-Za-z0-9]\+' | head -1)
        # echo "✅ Activity API key created successfully using adapter approach!"
    fi
else
    echo ""
    echo "⏭️  Skipping API key creation as requested"
fi

echo ""
echo "🎉 Demo database setup complete!"

if [ "$CREATE_API_KEYS" = true ]; then
    echo ""
    echo "You can now test the server using the Python client."
    echo ""
    echo "================================================================"
    echo "CLIENT SETUP INSTRUCTIONS:"
    echo "================================================================"
    echo ""
    echo "Run these commands to set up and start the client:"
    echo ""
    echo "  cd $PROJECT_ROOT/clients/python"
    echo "  python -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "Alternatively, you can install the pip package directly:"
    echo ""
    echo "  pip install schmitech-orbit-client"
    echo ""
    echo "Then run this command to chat with your ORBIT assistant:"
    echo ""
    echo "  orbit-chat --url $SERVER_URL --api-key $CITY_API_KEY"
    echo ""
    echo "================================================================"
    echo "ADAPTER-BASED API KEYS:"
    echo "================================================================"
    echo "City API KEY (using adapter '$ADAPTER_NAME'): $CITY_API_KEY"
    # if [ "$DATASOURCE" = "chroma" ]; then
    #     echo ""
    #     echo "Activity API KEY (using adapter 'qa-vector-chroma'): $ACTIVITY_API_KEY"
    # fi
    echo ""
    echo "Note: This script now uses the new adapter-based approach."
    echo "      The old --collection method is deprecated but still supported."
    echo "================================================================"
fi

echo ""
echo "Happy orbiting! 🚀"
