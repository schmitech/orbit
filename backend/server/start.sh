#!/bin/bash

# Set environment variables for better MPS performance
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0  # Allow PyTorch to allocate as much memory as needed

# Set Python path to include the current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Default values
HOST="0.0.0.0"
WORKERS="1"
RELOAD="false"
CONFIG_PATH=""
PORT_OVERRIDE=""

# Parse named arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --host=*)
            HOST="${1#*=}"
            ;;
        --port=*)
            PORT_OVERRIDE="${1#*=}"
            ;;
        --workers=*)
            WORKERS="${1#*=}"
            ;;
        --reload)
            RELOAD="true"
            ;;
        --config=*)
            CONFIG_PATH="${1#*=}"
            ;;
        --host)
            HOST="$2"
            shift
            ;;
        --port)
            PORT_OVERRIDE="$2"
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift
            ;;
        --config)
            CONFIG_PATH="$2"
            shift
            ;;
        *)
            echo "Unknown parameter: $1"
            echo "Usage: $0 [--host=HOST] [--port=PORT] [--workers=N] [--reload] [--config=CONFIG_PATH]"
            exit 1
            ;;
    esac
    shift
done

# Default config file path if not specified
if [ -z "$CONFIG_PATH" ]; then
    CONFIG_PATH="../config/config.yaml"
    # Try alternate locations if the first one doesn't exist
    if [ ! -f "$CONFIG_PATH" ]; then
        CONFIG_PATH="../../backend/config/config.yaml"
    fi
    if [ ! -f "$CONFIG_PATH" ]; then
        CONFIG_PATH="config.yaml"
    fi
fi

echo "Looking for config file at: $CONFIG_PATH"

# Check if the config file exists
if [ ! -f "$CONFIG_PATH" ]; then
    echo "Warning: Config file not found at $CONFIG_PATH. Using default settings."
    PORT="3000"  # Default port if no config found
else
    # Load configuration from config.yaml to get port settings
    # Use Python to parse the YAML file
    HTTPS_ENABLED=$(python -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('enabled', False))
")
    
    if [ "$HTTPS_ENABLED" = "True" ]; then
        # Get HTTPS port from config
        PORT=$(python -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('port', 3443))
")
    else
        # Get HTTP port from config
        PORT=$(python -c "
import yaml
with open('$CONFIG_PATH') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('port', 3000))
")
    fi
fi

# Use port override if specified
if [ -n "$PORT_OVERRIDE" ]; then
    echo "Overriding port from config with command line parameter: $PORT_OVERRIDE"
    PORT="$PORT_OVERRIDE"
fi

# Prepare environment variables to override config settings
export OIS_HOST="$HOST"
export OIS_PORT="$PORT"

echo "Starting server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Reload: $RELOAD"
echo "Config path: $CONFIG_PATH"
echo "PYTHONPATH: $PYTHONPATH"

# Get the directory structure to determine the module path
# If server.py is in a subdirectory like 'server', we need to adjust
MODULE_PATH="server:app"  # Default
if [ -d "server" ] && [ -f "server/server.py" ]; then
    MODULE_PATH="server.server:app"
fi

# Build the command to run
if [ "$RELOAD" = "true" ]; then
    # For development with reload, use uvicorn directly with the main app instance
    UVICORN_CMD="uvicorn $MODULE_PATH --host $HOST --port $PORT --reload"
else
    # For production, use our main.py script which creates the InferenceServer
    if [ "$WORKERS" -gt "1" ]; then
        # Use create_app for multi-worker mode
        CREATE_APP_PATH=${MODULE_PATH%:*}":create_app"
        UVICORN_CMD="uvicorn $CREATE_APP_PATH --host $HOST --port $PORT --workers $WORKERS"
        
        # Add config path if specified
        if [ -n "$CONFIG_PATH" ]; then
            # We can't pass params directly to the create_app function in this syntax,
            # so we'll rely on environment variables
            export OIS_CONFIG_PATH="$CONFIG_PATH"
            echo "Setting OIS_CONFIG_PATH environment variable to: $CONFIG_PATH"
        fi
    else
        # Single worker - use the Python command
        if [ -n "$CONFIG_PATH" ]; then
            PYTHON_CMD="python main.py --config \"$CONFIG_PATH\""
        else
            PYTHON_CMD="python main.py"
        fi
        UVICORN_CMD="$PYTHON_CMD"
    fi
fi

# Run the server
echo "Executing: $UVICORN_CMD"
eval "$UVICORN_CMD"