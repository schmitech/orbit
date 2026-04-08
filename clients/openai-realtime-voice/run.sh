#!/bin/bash
#
# ORBIT OpenAI Realtime Voice Client
# =====================================
#
# Usage:
#   ./run.sh          Start the development server (port 5175)
#   ./run.sh build    Build for production
#   ./run.sh install  Install dependencies
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

case "$1" in
    install)
        echo "Installing dependencies..."
        npm install
        ;;
    build)
        echo "Building for production..."
        npm run build
        ;;
    *)
        if [ ! -d "node_modules" ]; then
            echo "Installing dependencies first..."
            npm install
        fi

        echo ""
        echo "Starting OpenAI Realtime Voice test client..."
        echo ""
        echo "  Prerequisites:"
        echo "    1. ORBIT server running (e.g. ws://localhost:3000)"
        echo "    2. Adapter open-ai-real-time-voice-chat enabled + audio.yaml imported"
        echo "    3. OPENAI_API_KEY set on the server"
        echo ""
        echo "  Dev server: http://localhost:5175"
        echo ""

        npm run dev
        ;;
esac
