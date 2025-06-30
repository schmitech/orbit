#!/bin/bash

# ORBIT CLI Bash Wrapper
# This wrapper ensures the Python CLI runs with the correct environment

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Set up Python path to include the server directory
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Check if we're in a virtual environment, if not try to activate one
if [[ -z "$VIRTUAL_ENV" ]]; then
    # Check for common virtual environment locations
    if [[ -f "${SCRIPT_DIR}/../venv/bin/activate" ]]; then
        source "${SCRIPT_DIR}/../venv/bin/activate"
    elif [[ -f "${SCRIPT_DIR}/../.venv/bin/activate" ]]; then
        source "${SCRIPT_DIR}/../.venv/bin/activate"
    fi
fi

# Make the Python script executable if it isn't already
chmod +x "$SCRIPT_DIR/orbit.py"

# Forward all arguments to the Python script
exec python3 "$SCRIPT_DIR/orbit.py" "$@"