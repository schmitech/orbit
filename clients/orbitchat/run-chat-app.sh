#!/bin/bash
#
# OrbitChat Daemon Control Script
# ================================
#
# Usage:
#   ./run-chat-app.sh --start [port]    Start orbitchat in background
#   ./run-chat-app.sh --stop            Stop orbitchat
#   ./run-chat-app.sh --restart [port]  Restart orbitchat
#   ./run-chat-app.sh --status          Check if orbitchat is running
#   ./run-chat-app.sh --help            Show this help message
#
# All application settings are in orbitchat.yaml (next to this script).
# Only adapter secrets (API keys) are set here via VITE_ADAPTERS.
#
# Files:
#   PID file: <script_dir>/orbitchat.pid
#   Log file: <script_dir>/orbitchat.log
#

# Get the directory where this script is located (works on Mac and Linux)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PIDFILE="$SCRIPT_DIR/orbitchat.pid"
LOGFILE="$SCRIPT_DIR/orbitchat.log"
PORT="${ORBITCHAT_PORT:-5173}"
CONFIG_FILE="orbitchat.yaml"
ACTION=""

export NODE_OPTIONS="--no-deprecation"

# Adapter secrets (API keys) — the only env var needed.
# All other settings live in orbitchat.yaml.

export VITE_ADAPTERS='[
  { "name": "Simple Chat","apiKey":"default-key","apiUrl":"http://localhost:3000"},
  { "name": "Chat With Files","apiKey":"multimodal","apiUrl":"http://localhost:3000"},
  { "name": "Tender Notices Agent", "apiKey": "tender-notices", "apiUrl": "http://localhost:3000" },
  { "name": "Award Notices Agent", "apiKey": "award-notices", "apiUrl": "http://localhost:3000" },
  { "name": "Contract History Agent", "apiKey": "contract-history", "apiUrl": "http://localhost:3000" },
  { "name": "Standing Offers Agent", "apiKey": "standing-offers", "apiUrl": "http://localhost:3000" },
  { "name": "Cross Domain", "apiKey": "canadabuys", "apiUrl": "http://localhost:3000" }
]'

start_app() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi

    echo "Starting orbitchat on port $PORT with config $CONFIG_FILE..."

    nohup orbitchat --port "$PORT" --host 0.0.0.0 --config "$CONFIG_FILE" \
        > "$LOGFILE" 2>&1 &

    echo $! > "$PIDFILE"
    echo ""
    echo "✓ orbitchat started (PID: $!)"
    echo ""
    echo "  Open in browser: http://localhost:$PORT"
    echo "  Logs: $LOGFILE"
    echo ""
}

stop_app() {
    if [ ! -f "$PIDFILE" ]; then
        echo "orbitchat is not running (no PID file)"
        exit 1
    fi

    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping orbitchat (PID: $PID)..."
        kill "$PID"
        rm -f "$PIDFILE"
        echo "orbitchat stopped"
    else
        echo "orbitchat is not running (stale PID file)"
        rm -f "$PIDFILE"
    fi
}

status_app() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is running (PID: $(cat "$PIDFILE"))"
        echo "  URL: http://localhost:$PORT"
        echo "  Config: $CONFIG_FILE"
    else
        echo "orbitchat is not running"
    fi
}

restart_app() {
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping orbitchat (PID: $PID)..."
            kill "$PID"
            sleep 1
        fi
        rm -f "$PIDFILE"
    fi
    start_app
}

show_help() {
    echo "OrbitChat Daemon Control Script"
    echo "================================"
    echo ""
    echo "Usage: $0 [options] {--start [port]|--stop|--restart [port]|--status|--help}"
    echo ""
    echo "Options:"
    echo "  --config [file]   Use specific YAML configuration file (default: orbitchat.yaml)"
    echo "  --start [port]    Start orbitchat in background (optionally specify port)"
    echo "  --stop            Stop orbitchat"
    echo "  --restart [port]  Restart orbitchat (optionally specify port)"
    echo "  --status          Check if orbitchat is running"
    echo "  --help            Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  ORBITCHAT_PORT    Port to run on (default: 5173)"
    echo ""
    echo "All application settings are in orbitchat.yaml by default."
    echo "Adapter secrets (API keys) are set via VITE_ADAPTERS env var in this script."
    echo ""
    echo "Examples:"
    echo "  $0 --start                      # Start on default port 5173"
    echo "  $0 --start 8080                 # Start on port 8080"
    echo "  $0 --config custom.yaml --start # Start with custom config"
    echo "  ORBITCHAT_PORT=8080 $0 --start  # Start on port 8080 (env var)"
    echo ""
    echo "Files (stored in script directory):"
    echo "  PID file: $PIDFILE"
    echo "  Log file: $LOGFILE"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --start)
            ACTION="start"
            shift
            if [[ -n "$1" && "$1" != --* ]]; then
                PORT="$1"
                shift
            fi
            ;;
        --stop)
            ACTION="stop"
            shift
            ;;
        --restart)
            ACTION="restart"
            shift
            if [[ -n "$1" && "$1" != --* ]]; then
                PORT="$1"
                shift
            fi
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --config)
            if [[ -n "$2" ]]; then
                CONFIG_FILE="$2"
                shift 2
            else
                echo "Error: --config requires a file path"
                exit 1
            fi
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            show_help
            exit 1
            ;;
    esac
done

case "$ACTION" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        restart_app
        ;;
    status)
        status_app
        ;;
    *)
        show_help
        exit 1
        ;;
esac
