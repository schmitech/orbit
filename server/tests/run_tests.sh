#!/bin/bash

# Change to the server directory
cd "$(dirname "$0")/.."

# Make sure Python can find the server modules
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Run the tests
python tests/run_tests.py 