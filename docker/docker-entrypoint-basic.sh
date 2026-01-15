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

# Start the ORBIT server in the background
echo "Starting ORBIT server..."
python /orbit/server/main.py --config /orbit/config/config.yaml &
ORBIT_PID=$!

# Wait for ORBIT server to be ready
echo "Waiting for ORBIT server to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! curl -s http://localhost:3000/health > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "Error: ORBIT server failed to start after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for ORBIT server... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "✓ ORBIT server is ready"

# Start orbitchat web app (direct mode with default API key)
echo "Starting orbitchat web app on port 5173..."

orbitchat --api-url http://localhost:3000 --api-key default-key --host 0.0.0.0 &
ORBITCHAT_PID=$!

echo "✓ orbitchat web app started"
echo ""
echo "=========================================="
echo "  ORBIT Basic is ready!"
echo "  Web App: http://localhost:5173"
echo "  API:     http://localhost:3000"
echo "=========================================="
echo ""

# Handle shutdown gracefully
trap "echo 'Shutting down...'; kill $ORBITCHAT_PID $ORBIT_PID $OLLAMA_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# Wait for any process to exit
wait -n

# If any process exits, shut down all
echo "A process exited, shutting down..."
kill $ORBITCHAT_PID $ORBIT_PID $OLLAMA_PID 2>/dev/null
exit 1
