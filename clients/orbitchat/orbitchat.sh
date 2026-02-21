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
# Only adapter secrets (API keys) are set here via ORBIT_ADAPTER_KEYS.
#
# Files:
#   PID file: <state_dir>/orbitchat.pid
#   Log file: <state_dir>/orbitchat.log
#

# Get the directory where this script is located (works on Mac and Linux)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Runtime state directory (log + pid), overridable via ORBITCHAT_STATE_DIR.
if [ -n "${ORBITCHAT_STATE_DIR:-}" ]; then
    STATE_DIR="$ORBITCHAT_STATE_DIR"
elif [ -n "${XDG_STATE_HOME:-}" ]; then
    STATE_DIR="$XDG_STATE_HOME/orbitchat"
else
    STATE_DIR="$HOME/.local/state/orbitchat"
fi

if ! mkdir -p "$STATE_DIR" 2>/dev/null; then
    STATE_DIR="/tmp/orbitchat-${USER:-$(id -u)}"
    mkdir -p "$STATE_DIR" || {
        echo "Error: could not create state directory for PID/log files."
        exit 1
    }
fi

PIDFILE="$STATE_DIR/orbitchat.pid"
LOGFILE="$STATE_DIR/orbitchat.log"
PORT="${ORBITCHAT_PORT:-5173}"
CONFIG_FILE="$SCRIPT_DIR/orbitchat.yaml"
ACTION=""
FORCE_RESTART=false

# ... (parsing logic happens below, we will update PIDFILE/LOGFILE after parsing)

# When installed as an npm package, default config often lives in current directory.
if [ ! -f "$CONFIG_FILE" ] && [ -f "$(pwd)/orbitchat.yaml" ]; then
    CONFIG_FILE="$(pwd)/orbitchat.yaml"
fi

export NODE_OPTIONS="--no-deprecation"

# All application settings are in orbitchat.yaml.
# Secrets (API keys) should be set in .env or exported in your terminal
# as ORBIT_ADAPTER_KEYS or VITE_ADAPTER_KEYS.

start_app() {
    # Update PID and Log files based on the actual port
    PIDFILE="$STATE_DIR/orbitchat-${PORT}.pid"
    LOGFILE="$STATE_DIR/orbitchat-${PORT}.log"
    LEGACY_LOGFILE="$STATE_DIR/orbitchat.log"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: config file not found: $CONFIG_FILE"
        exit 1
    fi

    # Determine the executable to use
    local orbitchat_cmd="orbitchat"
    if [ -x "$SCRIPT_DIR/bin/orbitchat.js" ]; then
        orbitchat_cmd="$SCRIPT_DIR/bin/orbitchat.js"
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

    # Always start with a fresh per-port log and keep a legacy pointer updated.
    : > "$LOGFILE"
    rm -f "$LEGACY_LOGFILE"
    ln -s "$(basename "$LOGFILE")" "$LEGACY_LOGFILE" 2>/dev/null || cp "$LOGFILE" "$LEGACY_LOGFILE"

    echo "Starting orbitchat on port $PORT with config $CONFIG_FILE..."

    nohup "$orbitchat_cmd" --port "$PORT" --host 0.0.0.0 --config "$CONFIG_FILE" \
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
    PIDFILE="$STATE_DIR/orbitchat-${PORT}.pid"
    LOGFILE="$STATE_DIR/orbitchat-${PORT}.log"
    local pids=""
    if [ -f "$PIDFILE" ]; then
        pids=$(cat "$PIDFILE")
    fi

    # Supplement or fallback to lsof if PID file is missing or doesn't match a running process
    if command -v lsof >/dev/null 2>&1; then
        local port_pids
        port_pids=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | xargs)
        pids="$pids $port_pids"
    fi

    # Filter for unique running PIDs
    local running_pids=""
    if [ -n "$pids" ]; then
        local unique_pids
        unique_pids=$(echo "$pids" | tr ' ' '\n' | sort -u | xargs)
        local filtered_pids=""
        for p in $unique_pids; do
            if kill -0 "$p" 2>/dev/null; then
                filtered_pids="$filtered_pids $p"
            fi
        done
        running_pids=$(echo "$filtered_pids" | xargs)
    fi

    if [ -z "$running_pids" ]; then
        echo "orbitchat is not running"
        rm -f "$PIDFILE"
        if [ "$ACTION" = "stop" ]; then
            exit 1
        fi
        return 0
    fi

    echo "Stopping orbitchat (PID(s): $running_pids)..."
    kill $running_pids 2>/dev/null || true

    # Wait for up to 5 seconds for the processes to exit
    local timeout=5
    while [ $timeout -gt 0 ]; do
        local still_running=false
        for p in $running_pids; do
            if kill -0 "$p" 2>/dev/null; then
                still_running=true
                break
            fi
        done
        if [ "$still_running" = false ]; then
            break
        fi
        sleep 1
        ((timeout--))
    done

    # If still running, force kill
    for p in $running_pids; do
        if kill -0 "$p" 2>/dev/null; then
            echo "Process $p did not stop gracefully. Sending SIGKILL..."
            kill -9 "$p" 2>/dev/null || true
        fi
    done

    rm -f "$PIDFILE"
    echo "orbitchat stopped"
}

status_app() {
    PIDFILE="$STATE_DIR/orbitchat-${PORT}.pid"
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
    stop_app
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
    echo "  --stop [port]     Stop orbitchat (optionally specify port)"
    echo "  --restart [port]  Restart orbitchat (optionally specify port)"
    echo "  --status          Check if orbitchat is running"
    echo "  --help            Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  ORBITCHAT_PORT       Port to run on (default: 5173)"
    echo "  ORBITCHAT_STATE_DIR  Directory for PID/log files"
    echo ""
    echo "All application settings are in orbitchat.yaml by default."
    echo "Adapter secrets (API keys) are set via ORBIT_ADAPTER_KEYS env var in this script."
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
    echo "Files (stored in state directory):"
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
            if [[ -n "$1" && "$1" != --* ]]; then
                PORT="$1"
                shift
            fi
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
