#!/bin/bash

# Configuration
MODEL_PATH="../orbit/models/gemma-4-E2B-it-Q4_K_M.gguf"
PORT=8080
BINARY="./build/bin/llama-server"

# Check if binary exists
if [ ! -f "$BINARY" ]; then
    echo "Error: $BINARY not found. Please make sure you have built the project."
    exit 1
fi

# Check if model exists
if [ ! -f "$MODEL_PATH" ]; then
    echo "Error: Model not found at $MODEL_PATH"
    exit 1
fi

echo "Starting llama-server on port $PORT with model $MODEL_PATH..."

# Run the server
"$BINARY" \
    --model "$MODEL_PATH" \
    --port "$PORT" \
    --ctx-size 16384 \
    --parallel 4 \
    "$@"
