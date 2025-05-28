#!/bin/bash

# Exit on any error
set -e

# Change to the server directory
cd "$(dirname "$0")/.." || exit 1

# Get absolute path of server directory
SERVER_DIR=$(pwd)

# Make sure Python can find the server modules
export PYTHONPATH="${SERVER_DIR}:${PYTHONPATH:-}"

# Check if pytest is installed
if ! python3 -c "import pytest" &> /dev/null; then
    echo "Error: pytest is not installed. Please install it with: pip install pytest"
    exit 1
fi

# Run the tests
echo "Running tests from ${SERVER_DIR}/tests..."
python3 tests/run_tests.py 