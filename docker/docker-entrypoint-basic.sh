#!/bin/bash
set -e

echo "Starting ORBIT Basic with Ollama..."

# Start Ollama in the background
echo "Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: Ollama failed to start after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for Ollama... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "✓ Ollama is ready"

# Verify granite4:1b model is available
echo "Checking for granite4:1b model..."
if ollama list | grep -q "granite4:1b"; then
    echo "✓ Model granite4:1b is available"
else
    echo "Model not found, pulling granite4:1b..."
    ollama pull granite4:1b
    echo "✓ Model granite4:1b pulled successfully"
fi

# Verify nomic-embed-text model is available for embeddings
echo "Checking for nomic-embed-text model..."
if ollama list | grep -q "nomic-embed-text"; then
    echo "✓ Model nomic-embed-text is available"
else
    echo "Model not found, pulling nomic-embed-text:latest..."
    ollama pull nomic-embed-text:latest
    echo "✓ Model nomic-embed-text pulled successfully"
fi

# Start the ORBIT server with default config
echo "Starting ORBIT server..."
exec python /orbit/server/main.py --config /orbit/config/config.yaml
