#!/bin/bash

# Set environment variables for better MPS performance
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0  # Allow PyTorch to allocate as much memory as needed

# Set Python path to include the current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Default values
HOST="0.0.0.0"
PORT="3000"
WORKERS="1"
RELOAD="false"

# Parse named arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --host=*)
            HOST="${1#*=}"
            ;;
        --port=*)
            PORT="${1#*=}"
            ;;
        --workers=*)
            WORKERS="${1#*=}"
            ;;
        --reload)
            RELOAD="true"
            ;;
        --host)
            HOST="$2"
            shift
            ;;
        --port)
            PORT="$2"
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift
            ;;
        *)
            echo "Unknown parameter: $1"
            echo "Usage: $0 [--host=HOST] [--port=PORT] [--workers=N] [--reload]"
            exit 1
            ;;
    esac
    shift
done

# Load configuration from config.yaml
CONFIG_FILE="../config/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    # Use Python to parse the YAML file
    HTTPS_ENABLED=$(python -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('enabled', False))
")
    
    if [ "$HTTPS_ENABLED" = "True" ]; then
        # Get HTTPS configuration
        HTTPS_PORT=$(python -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('port', 3443))
")
        SSL_CERTFILE=$(python -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('cert_file', ''))
")
        SSL_KEYFILE=$(python -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    print(config.get('general', {}).get('https', {}).get('key_file', ''))
")
        
        # Use HTTPS configuration
        PORT=$HTTPS_PORT
        SSL_ARGS="--ssl-keyfile $SSL_KEYFILE --ssl-certfile $SSL_CERTFILE"
    else
        SSL_ARGS=""
    fi
else
    SSL_ARGS=""
fi

echo "Starting server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Reload: $RELOAD"
echo "PYTHONPATH: $PYTHONPATH"
if [ -n "$SSL_ARGS" ]; then
    echo "HTTPS enabled with certificates"
fi

# Start uvicorn with the parsed arguments
if [ "$RELOAD" = "true" ]; then
    uvicorn server:app --host "$HOST" --port "$PORT" --workers "$WORKERS" --reload $SSL_ARGS
else
    uvicorn server:app --host "$HOST" --port "$PORT" --workers "$WORKERS" $SSL_ARGS
fi