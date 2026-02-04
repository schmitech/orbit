#!/usr/bin/env bash
# Start the Moshi/PersonaPlex server the same way as Docker.
# Run from the personaplex repo root.
#
# Usage:
#   ./start-moshi-server.sh [options]
#   ./start-moshi-server.sh --start      # start in foreground (default)
#   ./start-moshi-server.sh --daemon     # start in background
#   ./start-moshi-server.sh --stop       # stop daemon
#   ./start-moshi-server.sh --status     # show if server is running
#
# Options: --start | --stop | --status | --daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="${SCRIPT_DIR}/moshi-server.pid"
LOG_FILE="${SCRIPT_DIR}/moshi-server.log"
PORT="${PORT:-8998}"

# Load .env (HF_TOKEN, etc.) if present
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

# Match docker-compose: disable torch compile to reduce memory and avoid compile delays
export NO_TORCH_COMPILE=1

# SSL directory for HTTPS (Docker uses /app/ssl; we use a local dir so certs persist)
SSL_DIR="${SSL_DIR:-./ssl}"
mkdir -p "$SSL_DIR"

# Use venv if present (Docker uses /app/moshi/.venv)
if [[ -x moshi/.venv/bin/python ]]; then
  PYTHON="moshi/.venv/bin/python"
elif [[ -x .venv/bin/python ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python"
fi

cmd=""
for arg in "$@"; do
  case "$arg" in
    --start)  cmd=start;  break ;;
    --stop)   cmd=stop;   break ;;
    --status) cmd=status; break ;;
    --daemon) cmd=daemon; break ;;
    --help|-h) cmd=help;  break ;;
  esac
done
# Default to start (foreground) for backward compatibility
[[ -z "$cmd" ]] && cmd=start

# --- help: display usage ---
do_help() {
  echo "Usage: $(basename "$0") [OPTION]"
  echo ""
  echo "Start, stop, or query the Moshi/PersonaPlex server. Run from the personaplex repo root."
  echo ""
  echo "Options:"
  echo "  --start     Start server in foreground (default)"
  echo "  --daemon    Start server in background (log: moshi-server.log)"
  echo "  --stop      Stop the server if running as daemon"
  echo "  --status    Show whether the server is running"
  echo "  --help, -h  Show this help"
  echo ""
  echo "Environment: PORT (default 8998), SSL_DIR (default ./ssl)"
}

# --- status: show if server is running ---
do_status() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "status: not running (no PID file)"
    return 0
  fi
  pid=$(cat "$PID_FILE")
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "status: not running (stale PID $pid)"
    rm -f "$PID_FILE"
    return 0
  fi
  echo "status: running (PID $pid, port $PORT)"
  return 0
}

# --- stop: kill daemon if running ---
do_stop() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "Moshi server not running (no PID file)."
    return 0
  fi
  pid=$(cat "$PID_FILE")
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Moshi server not running (stale PID $pid). Removing PID file."
    rm -f "$PID_FILE"
    return 0
  fi
  echo "Stopping Moshi server (PID $pid)..."
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Forcing kill (SIGKILL)."
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Stopped."
}

# --- GPU check (shared by start and daemon) ---
check_gpu() {
  echo "Using: $PYTHON"
  echo "SSL dir: $SSL_DIR"
  echo "--- GPU / CUDA check ---"
  if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || nvidia-smi
  else
    echo "nvidia-smi not found (driver not installed or not in PATH)"
  fi
  CUDA_STATUS=$("$PYTHON" -c "
import torch
print('PyTorch version:', torch.__version__)
print('CUDA available:', torch.cuda.is_available())
print('CUDA device count:', torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    print('  GPU', i, ':', torch.cuda.get_device_name(i))
" 2>&1) || true
  echo "$CUDA_STATUS"
  if ! "$PYTHON" -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
    echo "---"
    echo "No CUDA GPU visible to PyTorch. Possible causes:"
    echo "  - No GPU on this machine"
    echo "  - NVIDIA driver not installed (install and reboot)"
    echo "  - PyTorch installed without CUDA (reinstall with: pip install torch --index-url https://download.pytorch.org/whl/cu124)"
    echo "  - Running in a VM/container without GPU passthrough"
    exit 1
  fi
  echo "---"
}

# --- run server (foreground) ---
run_server() {
  exec "$PYTHON" -m moshi.server --ssl "$SSL_DIR" --host 0.0.0.0 --port "$PORT"
}

# --- start: foreground ---
do_start() {
  check_gpu
  echo "Starting Moshi server on 0.0.0.0:${PORT} (foreground). Use Ctrl+C to stop."
  echo "To run in background instead: $(basename "$0") --daemon"
  run_server
}

# --- daemon: background ---
do_daemon() {
  if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Moshi server already running (PID $pid). Use --stop first."
      exit 1
    fi
    rm -f "$PID_FILE"
  fi
  check_gpu
  echo "Starting Moshi server on 0.0.0.0:${PORT} (daemon, log: $LOG_FILE)..."
  nohup "$PYTHON" -m moshi.server --ssl "$SSL_DIR" --host 0.0.0.0 --port "$PORT" >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Started (PID $(cat "$PID_FILE")). Use --status or --stop."
}

case "$cmd" in
  help)   do_help ;;
  status) do_status ;;
  stop)   do_stop ;;
  start)  do_start ;;
  daemon) do_daemon ;;
  *)      echo "Unknown command: $cmd"; exit 1 ;;
esac
