#!/bin/bash

# PostgreSQL RAG System - Streamlit Demo Launcher
echo "🚀 Starting PostgreSQL RAG System - Streamlit Demo"
echo "=================================================="

# Note: .env file is optional - the system will use defaults if not found
echo "ℹ️  Note: Create a .env file for custom configuration (optional)"
echo "   The system will use sensible defaults if no .env file is found."
echo ""

# Check if Ollama is running (read URL from .env if available)
echo "🔍 Checking Ollama server..."

# Read Ollama URL from .env file if it exists
OLLAMA_URL="http://localhost:11434"
if [ -f .env ]; then
    ENV_OLLAMA_URL=$(grep "^OLLAMA_BASE_URL=" .env | cut -d'=' -f2)
    if [ ! -z "$ENV_OLLAMA_URL" ]; then
        OLLAMA_URL="$ENV_OLLAMA_URL"
    fi
fi

echo "   Checking: $OLLAMA_URL"

if ! curl -s "$OLLAMA_URL/api/tags" > /dev/null; then
    echo "❌ Error: Ollama server is not responding at $OLLAMA_URL"
    echo "Please ensure Ollama is running and accessible."
    echo ""
    echo "If using a remote server, check:"
    echo "  - Network connectivity"
    echo "  - Firewall settings"
    echo "  - Server status"
    exit 1
fi

echo "✅ Ollama server is running at $OLLAMA_URL"

echo "🌐 Starting Streamlit demo..."
echo "The demo will open in your browser at: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the demo"
echo ""

streamlit run streamlit_demo.py --server.port 8501 --server.address 0.0.0.0 