#!/usr/bin/env bash
# Build and install PersonaPlex without Docker (same deps as Dockerfile).
# Run from the personaplex repo root. Requires: libopus-dev, Python 3.10+, uv or pip.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== PersonaPlex native setup (no Docker) ==="

# 1) System deps (optional check)
if ! pkg-config --exists opus 2>/dev/null; then
  echo "Install Opus dev library, e.g.: sudo apt install libopus-dev"
  exit 1
fi

# 2) Install moshi and optional accelerate for --cpu-offload
if command -v uv &>/dev/null; then
  echo "Using uv..."
  cd moshi
  uv venv .venv --python 3.12
  uv sync
  uv pip install --python .venv/bin/python accelerate
  cd ..
  echo "Done. Start server with: ./start-moshi-server.sh"
else
  echo "Using pip..."
  pip install "moshi/."
  pip install accelerate
  echo "Done. Start server with: ./start-moshi-server.sh"
fi
