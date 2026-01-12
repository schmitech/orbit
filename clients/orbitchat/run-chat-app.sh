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

# Set the VITE_ADAPTERS environment variable (required for --enable-api-middleware)
export VITE_ADAPTERS='[
  { "name": "Simple Chat", "apiKey": "default-key", "apiUrl": "http://localhost:3001", "description": "Basic chat interface using the default conversational agent." },
  { "name": "City QA Chat (SQLite)", "apiKey": "orbit_md9B2sI60Igwq3k4Xm1zxhCypPXKrRcf", "apiUrl": "http://localhost:3001", "description": "Simple QA interface for a city database (SQLite)." },
  { "name": "City QA Chat (Chroma Vector)", "apiKey": "orbit_8qiDW2WfsCiQrFCcRDaoNwLkudx9XysX", "apiUrl": "http://localhost:3001", "description": "Simple QA interface for a city vector DB (Chroma)." },
  { "name": "Files Chat", "apiKey": "multimodal", "apiUrl": "http://localhost:3001", "description": "Supports chatting with document uploads and multimodal queries." },
  { "name": "HR System", "apiKey": "hr", "apiUrl": "http://localhost:3001", "description": "Conversational assistant for HR records, people search, and analytics." },
  { "name": "Movies DB", "apiKey": "mflix", "apiUrl": "http://localhost:3001", "description": "Explores and queries a MongoDB-powered movies database (MFlix sample set)." },
  { "name": "Business Analytics", "apiKey": "analytical", "apiUrl": "http://localhost:3001", "description": "Analyze datasets and generate business intelligence reports." },
  { "name": "Electric Vehicle Population", "apiKey": "orbit_7KyFOuHIpD7EAQRJHRBwmJxxoKYJ2nkn", "apiUrl": "http://localhost:3001", "description": "Accesses statistics and insights about electric vehicle registrations." },
  { "name": "Paris Open Data", "apiKey": "orbit_xpckctsinXzXakpIvvCPplnzpqaQ6ikj", "apiUrl": "http://localhost:3001", "description": "Interact with Paris city open data for events, venues, and more." },
  { "name": "REST API", "apiKey": "rest", "apiUrl": "http://localhost:3001", "description": "Enables generic REST API exploration and data extraction." },
  { "name": "Composite Explorer", "apiKey": "orbit_zvjZUVCXkOAmCa1grVgL6G2xK1W1JXLP", "apiUrl": "http://localhost:3001", "description": "Routes queries across HR, EV Population and DuckDB Analytics databases." },
  { "name": "Composite Explorer (Full)", "apiKey": "orbit_gYrmXa9cyQnUi4mneapKkjO9B4rpi6zl", "apiUrl": "http://localhost:3001", "description": "Routes across SQL, DuckDB, MongoDB, and HTTP APIs for comprehensive search." }
]'

# export VITE_ADAPTERS='[
#   { "name": "GoC Proactive Data Disclosure", "apiKey": "orbit_2GLQ8hGOHkwMmiBi5KJcMI1BbLV9aVNR", "apiUrl": "http://localhost:3001", "description": "Queries data on government procurement contracts and expenditures." },
#   { "name": "Ottawa Crime Composite", "apiKey": "orbit_b5gnmnJ7xmZQNmk744PCqUnocQH3QeSa", "apiUrl": "http://localhost:3001", "description": "Explore and analyze Ottawa police criminal offences data." },
#   { "name": "GoC Proactive Data Disclosure", "apiKey": "orbit_2GLQ8hGOHkwMmiBi5KJcMI1BbLV9aVNR", "apiUrl": "http://localhost:3001", "description": "Queries data on government procurement contracts and expenditures." },
#   { "name": "Alberta Shelter Occupancy", "apiKey": "orbit_ZlQhDHP8W9Bnto55agIeze1gkRh2wE2R", "apiUrl": "http://localhost:3001", "description": "Accesses and analyzes shelter occupancy data for Alberta." },
#   { "name": "Government Contracts", "apiKey": "orbit_eOpgtqGnozmhsgNag161aCmViAlxAxBX", "apiUrl": "http://localhost:3001", "description": "Queries data on government procurement contracts and expenditures." },
#   { "name": "Government Travel Expenses", "apiKey": "orbit_9o9oe7PFo3vE2qa3UuWC4nB8qAZoswtb", "apiUrl": "http://localhost:3001", "description": "Examines and filters federal travel expenses and related data." },
#   { "name": "Ottawa Police Auto Theft", "apiKey": "orbit_RlaC7ra4flnVMznMHTu6qGtJfSPRRjfr", "apiUrl": "http://localhost:3001", "description": "Explores and analyzes Ottawa police auto theft statistics and data." },
#   { "name": "Government of Canada AI Register (MVP)", "apiKey": "orbit_uGbvdp8YKrTemUtXMxlt0W5pS0ob6MMl", "apiUrl": "http://localhost:3001", "description": "Explores and analyzes data from the Government of Canada AI Register." }
# ]'

# { "name": "Composite Explorer (Full)", "apiKey": "orbit_gYrmXa9cyQnUi4mneapKkjO9B4rpi6zl", "apiUrl": "http://localhost:3001", "description": "Routes across SQL, DuckDB, MongoDB, and HTTP APIs for comprehensive search." }

start_app() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "orbitchat is already running (PID: $(cat "$PIDFILE"))"
        exit 1
    fi

    echo "Starting orbitchat on port $PORT..."
    # Note: Add '--host 0.0.0.0' below to listen on all network interfaces (allow access from other devices)
    # --out-of-service-message "Please check back later." \
    # --application-name "My Custom App" \
    nohup orbitchat --api-url http://localhost:3001 --enable-api-middleware --enable-upload --enable-audio --enable-autocomplete \
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
        --application-description "ORBIT provides a specialized AI interface that allows anyone to ask plain-language questions and receive summarized, citation-backed answers drawn directly from official Canadian open data sources. Please read our [Terms and Conditions](https://schmitech.ai/en/civicchat) before using the service." \
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
    echo ""
    echo "Examples:"
    echo "  $0 --start                      # Start on default port 5173"
    echo "  $0 --start 8080                 # Start on port 8080"
    echo "  ORBITCHAT_PORT=8080 $0 --start  # Start on port 8080 (env var)"
    echo ""
    echo "Note:"
    echo "  To allow access from other devices on the network, add '--host 0.0.0.0'"
    echo "  to the orbitchat command in this script."
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
