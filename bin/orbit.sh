#!/bin/bash

# Server Control Bash Script
# This is a simple wrapper around the Python CLI tool

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure logs directory exists and is writable
LOGS_DIR="$SCRIPT_DIR/../logs"
mkdir -p "$LOGS_DIR"
chmod u+w "$LOGS_DIR"

# Make the Python script executable if it isn't already
chmod +x "$SCRIPT_DIR/orbit.py"

# Forward all arguments to the Python script
"$SCRIPT_DIR/orbit.py" "$@"