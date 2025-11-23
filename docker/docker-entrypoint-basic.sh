#!/bin/bash
set -e

# Verify model exists
MODEL_FILE="/orbit/models/gemma-3-1b-it-Q4_0.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    echo "Warning: Model file not found at $MODEL_FILE"
    echo "The container may not function correctly without the model."
fi

# Start the server with default config
exec python /orbit/server/main.py --config /orbit/config/config.yaml

