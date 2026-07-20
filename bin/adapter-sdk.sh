#!/bin/bash
#
# Frictionless launcher for the ORBIT Adapter SDK generator.
# Runs from anywhere: resolves the repo root and venv relative to this script,
# puts server/ on the import path, and forwards all args to adapter_sdk.cli.
#
#   bin/adapter-sdk --list
#   bin/adapter-sdk                       # interactive wizard
#   bin/adapter-sdk --spec fetch --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer the project venv; fall back to an active interpreter.
if [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/venv/bin/python"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

export PYTHONPATH="$REPO_ROOT/server${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m adapter_sdk.cli "$@"
