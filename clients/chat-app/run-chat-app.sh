#!/bin/bash
#
# OrbitChat Daemon Control Script
# ================================
#
# Usage:
#   ./run-chat-app.sh --start   Start orbitchat in background
#   ./run-chat-app.sh --stop    Stop orbitchat
#   ./run-chat-app.sh --status  Check if orbitchat is running
#   ./run-chat-app.sh --help    Show this help message
#
# Files:
#   PID file: /home/ubuntu/orbitchat/orbitchat.pid
#   Log file: /home/ubuntu/orbitchat/orbitchat.log
#

PIDFILE="/home/ubuntu/orbitchat/orbitchat.pid"
LOGFILE="/home/ubuntu/orbitchat/orbitchat.log"

# Set the VITE_ADAPTERS environment variable (required for --enable-api-middleware)
export VITE_ADAPTERS='[
  { "name": "Simple Chat", "apiKey": "default-key", "apiUrl": "http://localhost:3000" },
  { "name": "Files Chat", "apiKey": "multimodal", "apiUrl": "http://localhost:3000" }
]'

start_app() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi

    echo "Starting orbitchat in background..."
    nohup orbitchat --api-url http://localhost:3000 --enable-api-middleware --enable-upload \
        --host 0.0.0.0 \
        --max-conversations 5 \
        --max-messages-per-conversation 50 \
        --max-total-messages 200 \
        --max-files-per-conversation 3 \
        --max-file-size-mb 10 \
        --max-total-files 20 \
        --max-message-length 500 \
        > "$LOGFILE" 2>&1 &

    echo $! > "$PIDFILE"
    echo "orbitchat started (PID: $!)"
    echo "Logs: $LOGFILE"
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
    else
        echo "orbitchat is not running"
    fi
}

show_help() {
    echo "OrbitChat Daemon Control Script"
    echo "================================"
    echo ""
    echo "Usage: $0 {--start|--stop|--status|--help}"
    echo ""
    echo "Options:"
    echo "  --start   Start orbitchat in background"
    echo "  --stop    Stop orbitchat"
    echo "  --status  Check if orbitchat is running"
    echo "  --help    Show this help message"
    echo ""
    echo "Files:"
    echo "  PID file: $PIDFILE"
    echo "  Log file: $LOGFILE"
}

case "$1" in
    --start)
        start_app
        ;;
    --stop)
        stop_app
        ;;
    --status)
        status_app
        ;;
    --help)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
