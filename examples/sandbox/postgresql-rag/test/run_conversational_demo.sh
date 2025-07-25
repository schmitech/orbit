#!/bin/bash

# PostgreSQL RAG System - Conversational Demo Launcher
echo "🚀 Starting PostgreSQL RAG System - Conversational Demo"
echo "======================================================"

# Note: .env file is optional - the system will use defaults if not found
echo "ℹ️  Note: Create a .env file for custom configuration (optional)"
echo "   The system will use sensible defaults if no .env file is found."
echo ""

# Check if Ollama is running (read URL from .env if available)
echo "🔍 Checking Ollama server..."

# Read Ollama URL from .env file if it exists (look in parent directory)
OLLAMA_URL="http://localhost:11434"
if [ -f ../.env ]; then
    ENV_OLLAMA_URL=$(grep "^OLLAMA_BASE_URL=" ../.env | cut -d'=' -f2)
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

echo "💬 Starting Conversational demo..."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get the parent directory (postgresql-rag)
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Create a temporary Python wrapper script
cat > "$SCRIPT_DIR/temp_conversational_wrapper.py" << 'EOF'
#!/usr/bin/env python3
"""
Temporary wrapper to run conversational demo with proper imports
"""
import sys
import os
from pathlib import Path

# Add the parent directory to Python path
script_dir = Path(__file__).parent
parent_dir = script_dir.parent
sys.path.insert(0, str(parent_dir))

# Now import and run the conversational demo
if __name__ == "__main__":
    # Import the conversational demo module
    import conversational_demo
    
    # Run the main function
    conversational_demo.main()
EOF

# Change to the parent directory and run with the wrapper
cd "$PARENT_DIR"
PYTHONPATH="$PARENT_DIR" python "$SCRIPT_DIR/temp_conversational_wrapper.py"

# Clean up the temporary file
rm -f "$SCRIPT_DIR/temp_conversational_wrapper.py" 