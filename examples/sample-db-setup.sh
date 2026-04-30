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
# 3. Optionally create API keys for the adapters
# 4. Display setup instructions and API keys if created

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the project root (parent of examples directory)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SQLITE_DB_PATH="$PROJECT_ROOT/examples/sqlite/sqlite_db"
CHROMA_DB_PATH="$PROJECT_ROOT/examples/chroma/chroma_db"
CHROMA_CREATE_SCRIPT="$PROJECT_ROOT/utils/vector/chroma/create_qa_pairs_collection.py"
CITY_QA_DATA="$PROJECT_ROOT/examples/city-qa-pairs.json"
CITY_PROMPT_FILE="$PROJECT_ROOT/examples/prompts/examples/city/city-assistant-normal-prompt.md"
ACTIVITY_QA_DATA="$PROJECT_ROOT/examples/activity-qa-pairs.json"
ACTIVITY_PROMPT_FILE="$PROJECT_ROOT/examples/prompts/examples/activity/activity-assistant-normal-prompt.md"

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
    
    # Read use_local setting from imported datasource config when available.
    DATASOURCES_CONFIG_PATH="$(dirname "$CONFIG_PATH")/datasources.yaml"
    if [ ! -f "$DATASOURCES_CONFIG_PATH" ]; then
        DATASOURCES_CONFIG_PATH="$PROJECT_ROOT/config/datasources.yaml"
    fi

    if [ -f "$DATASOURCES_CONFIG_PATH" ]; then
        USE_LOCAL=$(python3 -c "
import yaml
with open('$DATASOURCES_CONFIG_PATH') as f:
    config = yaml.safe_load(f) or {}
    print(str(config.get('datasources', {}).get('chroma', {}).get('use_local', True)).lower())
")
        CONFIG_CHROMA_DB_PATH=$(python3 -c "
import yaml
from pathlib import Path
with open('$DATASOURCES_CONFIG_PATH') as f:
    config = yaml.safe_load(f) or {}
db_path = config.get('datasources', {}).get('chroma', {}).get('db_path', 'examples/chroma/chroma_db')
path = Path(db_path)
if not path.is_absolute():
    path = Path('$PROJECT_ROOT') / path
print(path)
")
        if [ -n "$CONFIG_CHROMA_DB_PATH" ]; then
            CHROMA_DB_PATH="$CONFIG_CHROMA_DB_PATH"
        fi
    else
        USE_LOCAL="true"
    fi

    # Read use_local setting from config as a fallback for legacy config layouts.
    if [ -z "$USE_LOCAL" ]; then
        USE_LOCAL=$(python3 -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(str(config.get('datasources', {}).get('chroma', {}).get('use_local', True)).lower())
")
    fi
fi

# Set default protocol if not set
if [ -z "$PROTOCOL" ]; then
    PROTOCOL="http"
fi

echo "🚀 Setting up sample QA collections..."

if [ "$DATASOURCE" = "sqlite" ]; then
    if [ ! -f "$PROJECT_ROOT/examples/sqlite/rag_cli.py" ]; then
        echo "❌ Error: SQLite setup script not found at $PROJECT_ROOT/examples/sqlite/rag_cli.py"
        exit 1
    fi
    if [ ! -f "$CITY_QA_DATA" ]; then
        echo "❌ Error: Sample Q&A data not found at $CITY_QA_DATA"
        exit 1
    fi

    # Remove existing SQLite database file or directory if it exists
    if [ -e "$SQLITE_DB_PATH" ]; then
        echo "Removing existing SQLite database..."
        rm -rf "$SQLITE_DB_PATH"
    fi

    # Create new SQLite database with sample data
    python3 "$PROJECT_ROOT/examples/sqlite/rag_cli.py" setup --db-path "$SQLITE_DB_PATH" --data-path "$CITY_QA_DATA"
else
    if [ ! -f "$CHROMA_CREATE_SCRIPT" ]; then
        echo "❌ Error: Chroma setup script not found at $CHROMA_CREATE_SCRIPT"
        exit 1
    fi
    if [ ! -f "$CITY_QA_DATA" ]; then
        echo "❌ Error: Sample Q&A data not found at $CITY_QA_DATA"
        exit 1
    fi

    # Remove existing Chroma database directory if it exists
    if [ "$USE_LOCAL" = "true" ]; then
        if [ -d "$CHROMA_DB_PATH" ]; then
            echo "Removing existing Chroma database..."
            rm -rf "$CHROMA_DB_PATH"
        fi
    fi

    # Create Chroma collections
    echo "Creating Chroma collections..."
    LOCAL_ARGS=()
    if [ "$USE_LOCAL" = "true" ]; then
        LOCAL_ARGS=(--local --db-path "$CHROMA_DB_PATH")
    fi
    
    # Load Q&A pairs
    python3 "$CHROMA_CREATE_SCRIPT" city "$CITY_QA_DATA" "${LOCAL_ARGS[@]}"
    
    # Uncomment to create sample activity collection if examples/activity-qa-pairs.json is present.
    # python3 "$CHROMA_CREATE_SCRIPT" activity "$ACTIVITY_QA_DATA" "${LOCAL_ARGS[@]}"
fi

echo "✅ Sample QA collections created."

if [ "$CREATE_API_KEYS" = true ]; then
    echo ""
    echo "🔑 Creating API keys for ORBIT adapters..."
    
    # Determine which adapter to use based on datasource
    if [ "$DATASOURCE" = "sqlite" ]; then
        ADAPTER_NAME="qa-sql"
        echo "  • Using adapter '$ADAPTER_NAME' for SQLite Q&A data"
    else
        ADAPTER_NAME="qa-vector-chroma"
        echo "  • Using adapter '$ADAPTER_NAME' for Chroma Q&A data"
    fi
    
    echo "  • Connecting to server on port $PORT"
    echo "  • Using prompt file '$CITY_PROMPT_FILE'"
    echo ""

    if [ ! -f "$CITY_PROMPT_FILE" ]; then
        echo "❌ Error: Prompt file not found at $CITY_PROMPT_FILE"
        exit 1
    fi

    # Create API key for the selected adapter
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
    echo "  • auth-status output:"
    echo "$AUTH_STATUS" | sed -E 's/orbit_[A-Za-z0-9]+/orbit_***MASKED***/g' | sed 's/^/    /'
    
    if echo "$AUTH_STATUS" | grep -qi 'not authenticated'; then
        echo "❌ Not authenticated. Please login first:"
        echo "  python $PROJECT_ROOT/bin/orbit.py login"
        echo "Then run this script again."
        exit 1
    elif echo "$AUTH_STATUS" | grep -qi 'authenticated'; then
        echo "✅ Authentication verified"
    else
        echo "❌ Could not determine authentication status. Please login first:"
        echo "  python $PROJECT_ROOT/bin/orbit.py login"
        echo "Then run this script again."
        exit 1
    fi
    
    # Create API key using the adapter name from config/adapters/qa.yaml
    echo ""
    echo "Creating API key..."
    echo "  • Adapter: $ADAPTER_NAME"
    echo "  • Key name: City Assistant"
    echo "  • Prompt name: Municipal Assistant Prompt"
    echo "  • Command: python3 $PROJECT_ROOT/bin/orbit.py key create --adapter $ADAPTER_NAME --name \"City Assistant\" --prompt-file $CITY_PROMPT_FILE --prompt-name \"Municipal Assistant Prompt\""
    echo "  • Waiting for orbit CLI response..."

    set +e
    API_KEY_OUTPUT=$(python3 "$PROJECT_ROOT/bin/orbit.py" key create \
      --adapter "$ADAPTER_NAME" \
      --name "City Assistant" \
      --notes "This is a sample API key for the City Assistant using adapter '$ADAPTER_NAME'." \
      --prompt-file "$CITY_PROMPT_FILE" \
      --prompt-name "Municipal Assistant Prompt" 2>&1)
    API_KEY_EXIT_CODE=$?
    set -e

    echo "  • orbit CLI exit code: $API_KEY_EXIT_CODE"
    if [ -n "$API_KEY_OUTPUT" ]; then
        echo "  • orbit CLI output:"
        echo "$API_KEY_OUTPUT" | sed -E 's/orbit_[A-Za-z0-9]+/orbit_***MASKED***/g' | sed 's/^/    /'
    else
        echo "  • orbit CLI output: <empty>"
    fi

    if [ "$API_KEY_EXIT_CODE" -ne 0 ]; then
        echo "❌ Error: API key creation failed for adapter '$ADAPTER_NAME'."
        echo ""
        echo "Troubleshooting:"
        echo "  1. Confirm the adapter is enabled in config/adapters/qa.yaml."
        echo "  2. Confirm config/adapters.yaml imports adapters/qa.yaml."
        echo "  3. Restart the ORBIT server if adapter config changed after it started."
        echo "  4. Try manually: python3 $PROJECT_ROOT/bin/orbit.py key create --adapter $ADAPTER_NAME --name \"City Assistant\" --prompt-file \"$CITY_PROMPT_FILE\" --prompt-name \"Municipal Assistant Prompt\""
        exit "$API_KEY_EXIT_CODE"
    fi

    # Extract just the API key - properly capture orbit_ format keys
    CITY_API_KEY=$(echo "$API_KEY_OUTPUT" | grep -o 'orbit_[A-Za-z0-9]\+' | head -1)

    if [ -z "$CITY_API_KEY" ]; then
        echo "❌ Error: API key creation command succeeded, but no orbit_ key was found in the CLI output."
        echo "Please review the orbit CLI output above."
        exit 1
    fi

    echo "  • Extracted API key prefix: ${CITY_API_KEY:0:12}..."
    echo "✅ API key created successfully for adapter '$ADAPTER_NAME'!"

    # If using Chroma, create additional API key for activity collection
    if [ "$DATASOURCE" = "chroma" ]; then
        echo ""
        echo "🔑 Creating API key for activity collection..."
        echo "  • Using adapter 'qa-vector-chroma' for activity data"
        echo "  • Using prompt file '$ACTIVITY_PROMPT_FILE'"
        echo ""

        # Uncomment to generate an API key for the activity adapter.
        # ACTIVITY_API_KEY_OUTPUT=$(python3 "$PROJECT_ROOT/bin/orbit.py" key create \
        #   --adapter qa-vector-chroma \
        #   --name "Activity Assistant" \
        #   --notes "This is a sample API key for the Activity Assistant using adapter 'qa-vector-chroma'." \
        #   --prompt-file "$ACTIVITY_PROMPT_FILE" \
        #   --prompt-name "Activity Assistant Prompt")

        # ACTIVITY_API_KEY=$(echo "$ACTIVITY_API_KEY_OUTPUT" | grep -o 'orbit_[A-Za-z0-9]\+' | head -1)
        # echo "✅ Activity API key created successfully for adapter 'qa-vector-chroma'!"
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
    echo "  pip install -e ."
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
    echo "Note: API keys are associated with adapters from config/adapters/*.yaml."
    echo "================================================================"
fi

echo ""
echo "Happy orbiting! 🚀"
