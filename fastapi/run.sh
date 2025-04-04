#!/bin/bash

# Set environment variables for better MPS performance
export PYTORCH_ENABLE_MPS_FALLBACK=1
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0  # Allow PyTorch to allocate as much memory as needed

# Default values
HOST="0.0.0.0"
PORT="5001"
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

echo "Starting server..."
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Reload: $RELOAD"

# Start uvicorn with the parsed arguments
if [ "$RELOAD" = "true" ]; then
    uvicorn server:app --host "$HOST" --port "$PORT" --workers "$WORKERS" --reload
else
    uvicorn server:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
fi