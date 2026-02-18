#!/bin/bash
#
# OrbitChat Daemon Control Script
# ================================
#
# Usage:
#   ./run-chat-app.sh --start [port]  Start orbitchat in background
#   ./run-chat-app.sh --stop          Stop orbitchat
#   ./run-chat-app.sh --status        Check if orbitchat is running
#   ./run-chat-app.sh --help          Show this help message
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
ENABLE_AUDIO_OUTPUT="${ORBITCHAT_ENABLE_AUDIO_OUTPUT:-true}"
ENABLE_AUDIO_INPUT="${ORBITCHAT_ENABLE_AUDIO_INPUT:-true}"
VOICE_SILENCE_TIMEOUT_MS="${ORBITCHAT_VOICE_SILENCE_TIMEOUT_MS:-}"
VOICE_RECOGNITION_LANG="${ORBITCHAT_VOICE_RECOGNITION_LANG:-}"

# Set the VITE_ADAPTERS environment variable (adapter configs for the Express proxy)
export VITE_ADAPTERS='[
  { "name": "Simple Chat", "apiKey": "default-key", "apiUrl": "http://localhost:3000", "description": "Basic chat interface using the default conversational agent." },
  { "name": "City QA Chat (Chroma Vector)", "apiKey": "chroma-key", "apiUrl": "http://localhost:3000", "description": "Simple QA interface for a city vector DB (Chroma)." },
  { "name": "Files Chat", "apiKey": "multimodal", "apiUrl": "http://localhost:3000", "description": "Supports chatting with document uploads and multimodal queries." },
  { "name": "HR System", "apiKey": "hr", "apiUrl": "http://localhost:3000", "description": "Conversational assistant for HR records, people search, and analytics." },
  { "name": "Movies DB", "apiKey": "mflix", "apiUrl": "http://localhost:3000", "description": "Explores and queries a MongoDB-powered movies database (MFlix sample set)." },
  { "name": "Business Analytics", "apiKey": "analytical", "apiUrl": "http://localhost:3000", "description": "Analyze datasets and generate business intelligence reports." },
  { "name": "Electric Vehicle Population", "apiKey": "ev, "apiUrl": "http://localhost:3000", "description": "Accesses statistics and insights about electric vehicle registrations." },
  { "name": "Paris Open Data", "apiKey": "paris", "apiUrl": "http://localhost:3000", "description": "Interact with Paris city open data for events, venues, and more." },
  { "name": "REST API", "apiKey": "rest", "apiUrl": "http://localhost:3000", "description": "Enables generic REST API exploration and data extraction." }
]'

start_app() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi

    echo "Starting orbitchat on port $PORT..."
    AUDIO_OUTPUT_ARG=""
    AUDIO_INPUT_ARG=""
    VOICE_SILENCE_ARG=""
    VOICE_LANG_ARG=""
    if [ "$ENABLE_AUDIO_OUTPUT" = "true" ]; then
        AUDIO_OUTPUT_ARG="--enable-audio"
    fi
    if [ "$ENABLE_AUDIO_INPUT" = "true" ]; then
        AUDIO_INPUT_ARG="--enable-audio-input"
    fi
    if [ -n "$VOICE_SILENCE_TIMEOUT_MS" ]; then
        VOICE_SILENCE_ARG="--voice-silence-timeout-ms $VOICE_SILENCE_TIMEOUT_MS"
    fi
    if [ -n "$VOICE_RECOGNITION_LANG" ]; then
        VOICE_LANG_ARG="--voice-recognition-lang $VOICE_RECOGNITION_LANG"
    fi

    nohup orbitchat --api-url http://localhost:3000 --enable-upload --enable-autocomplete \
        $AUDIO_OUTPUT_ARG \
        $AUDIO_INPUT_ARG \
        $VOICE_SILENCE_ARG \
        $VOICE_LANG_ARG \
        --port "$PORT" \
        --host 0.0.0.0 \
        --max-conversations 5 \
        --max-messages-per-conversation 50 \
        --max-messages-per-thread 10 \
        --max-total-messages 200 \
        --max-files-per-conversation 3 \
        --max-file-size-mb 10 \
        --max-total-files 20 \
        --max-message-length 500 \
        --application-name "Welcome to ORBIT Local" \
        --application-description "ORBIT provides a specialized AI interface that allows anyone to ask plain-language questions and receive summarized, citation-backed answers drawn directly from data sources." \
        --default-input-placeholder "Ask ORBIT Local Anything..." \
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
    else
        echo "orbitchat is not running"
    fi
}

show_help() {
    echo "OrbitChat Daemon Control Script"
    echo "================================"
    echo ""
    echo "Usage: $0 {--start [port]|--stop|--status|--help}"
    echo ""
    echo "Options:"
    echo "  --start [port]  Start orbitchat in background (optionally specify port)"
    echo "  --stop    Stop orbitchat"
    echo "  --status  Check if orbitchat is running"
    echo "  --help    Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  ORBITCHAT_PORT  Port to run on (default: 5173)"
    echo "  ORBITCHAT_ENABLE_AUDIO_OUTPUT  Enable audio playback button (default: true)"
    echo "  ORBITCHAT_ENABLE_AUDIO_INPUT   Enable microphone input button (default: true)"
    echo "  ORBITCHAT_VOICE_SILENCE_TIMEOUT_MS  Silence timeout before auto-send (optional)"
    echo "  ORBITCHAT_VOICE_RECOGNITION_LANG    Speech recognition locale, e.g. en-US (optional)"
    echo ""
    echo "Examples:"
    echo "  $0 --start                      # Start on default port 5173"
    echo "  $0 --start 8080                 # Start on port 8080"
    echo "  ORBITCHAT_PORT=8080 $0 --start  # Start on port 8080 (env var)"
    echo ""
    echo "Files (stored in script directory):"
    echo "  PID file: $PIDFILE"
    echo "  Log file: $LOGFILE"
}

case "$1" in
    --start)
        # Optional port argument: --start [port]
        if [ -n "$2" ]; then
            PORT="$2"
        fi
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
