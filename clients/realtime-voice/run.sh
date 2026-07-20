#!/bin/bash
#
# ORBIT Realtime Voice Bridge — test client
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
        echo "Starting realtime voice bridge test client..."
        echo ""
        echo "  Prerequisites:"
        echo "    1. ORBIT server running (e.g. ws://localhost:3000)"
        echo "    2. A real-time STS adapter enabled in audio.yaml — e.g."
        echo "       open-ai-real-time-voice-chat (needs OPENAI_API_KEY) or"
        echo "       gemini-live-voice-chat (needs GOOGLE_API_KEY)"
        echo "    3. VITE_ADAPTER_NAME in .env.local set to that adapter's name"
        echo ""
        echo "  Dev server: http://localhost:5175"
        echo ""

        npm run dev
        ;;
esac
