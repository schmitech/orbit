#!/bin/bash
#
# OrbitChat Daemon Control Script
# ================================
#
# Usage:
#   ./orbitchat.sh --start [port]    Start orbitchat in background
#   ./orbitchat.sh --stop            Stop orbitchat
#   ./orbitchat.sh --restart [port]  Restart orbitchat
#   ./orbitchat.sh --force-restart [port]  Force-kill port listeners and restart
#   ./orbitchat.sh --status          Check if orbitchat is running
#   ./orbitchat.sh --help            Show this help message
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
CONFIG_FILE="$SCRIPT_DIR/orbitchat.yaml"
ACTION=""
FORCE_RESTART=false

# When installed as an npm package, default config often lives in current directory.
if [ ! -f "$CONFIG_FILE" ] && [ -f "$(pwd)/orbitchat.yaml" ]; then
    CONFIG_FILE="$(pwd)/orbitchat.yaml"
fi

export NODE_OPTIONS="--no-deprecation"

# Adapter secrets (API keys) — the only env var needed.
# All other settings live in orbitchat.yaml.

export ORBIT_ADAPTERS='[
  { "name": "Simple Chat","apiKey":"default-key","apiUrl":"http://localhost:3000"},
  { "name": "Chat With Files","apiKey":"multimodal","apiUrl":"http://localhost:3000"}
]'

start_app() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: config file not found: $CONFIG_FILE"
        exit 1
    fi

    if command -v lsof >/dev/null 2>&1; then
        local existing_pids
        existing_pids=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | xargs)
        if [ -n "$existing_pids" ]; then
            if [ "$FORCE_RESTART" = true ]; then
                echo "Port $PORT is in use by PID(s): $existing_pids. Stopping them (--force-restart)..."
                kill $existing_pids 2>/dev/null || true
                sleep 1

                existing_pids=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | xargs)
                if [ -n "$existing_pids" ]; then
                    echo "Port $PORT still in use by PID(s): $existing_pids. Sending SIGKILL..."
                    kill -9 $existing_pids 2>/dev/null || true
                    sleep 1
                fi

                existing_pids=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | xargs)
                if [ -n "$existing_pids" ]; then
                    echo "Error: failed to free port $PORT (still used by PID(s): $existing_pids)."
                    exit 1
                fi
                rm -f "$PIDFILE"
            else
                echo "Error: port $PORT is already in use by PID(s): $existing_pids."
                echo "Stop the existing process first (or use --force-restart)."
                exit 1
            fi
        fi
    fi

    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi

    echo "Starting orbitchat on port $PORT with config $CONFIG_FILE..."

    nohup orbitchat --port "$PORT" --host 0.0.0.0 --config "$CONFIG_FILE" \
        > "$LOGFILE" 2>&1 &

    local started_pid=$!
    echo "$started_pid" > "$PIDFILE"
    sleep 1

    if ! kill -0 "$started_pid" 2>/dev/null; then
        echo "Failed to start orbitchat (process exited early)."
        echo "Last log lines:"
        tail -n 40 "$LOGFILE" 2>/dev/null || true
        rm -f "$PIDFILE"
        exit 1
    fi

    echo ""
    echo "✓ orbitchat started (PID: $started_pid)"
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
        if command -v lsof >/dev/null 2>&1; then
            local port_pid
            port_pid=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1)
            if [ -n "$port_pid" ]; then
                echo "orbitchat PID file is stale, but port $PORT is active (PID: $port_pid)."
                echo "  URL: http://localhost:$PORT"
                echo "  Config (requested): $CONFIG_FILE"
                return
            fi
        fi
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
    echo "Usage: $0 [options] {--start [port]|--stop|--restart [port]|--force-restart [port]|--status|--help}"
    echo ""
    echo "Options:"
    echo "  --config [file]   Use specific YAML configuration file (default: orbitchat.yaml)"
    echo "  --force-restart [port]  Kill any process using the target port, then restart"
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
    echo "  $0 --force-restart              # Force free default port, then restart"
    echo "  $0 --force-restart 8080         # Force free port 8080, then restart"
    echo "  $0 --force-restart --start      # Also works as a flag before --start"
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
        --force-restart)
            FORCE_RESTART=true
            if [[ -n "$2" && "$2" != --* ]]; then
                PORT="$2"
                shift 2
            else
                shift
            fi
            if [[ -z "$ACTION" ]]; then
                ACTION="force-restart"
            fi
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --config)
            if [[ -n "$2" ]]; then
                if [[ "$2" = /* ]]; then
                    CONFIG_FILE="$2"
                else
                    CONFIG_FILE="$(cd "$(pwd)" && pwd)/$2"
                fi
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
    force-restart)
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
