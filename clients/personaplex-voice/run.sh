#!/bin/bash
#
# ORBIT PersonaPlex Voice Client
# ================================
#
# Quick start script for development
#
# Usage:
#   ./run.sh          Start the development server
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
        # Check if node_modules exists
        if [ ! -d "node_modules" ]; then
            echo "Installing dependencies first..."
            npm install
        fi

        echo ""
        echo "Starting ORBIT PersonaPlex Voice Client..."
        echo ""
        echo "  Prerequisites:"
        echo "    1. ORBIT server running (ws://localhost:3000)"
        echo "    2. PersonaPlex adapter enabled"
        echo "    3. PersonaPlex GPU server accessible"
        echo ""

        npm run dev
        ;;
esac
