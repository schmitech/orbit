#!/bin/bash

# Script to build the widget with a custom configuration
# Usage: ./custom-build.sh [path/to/config.json]

# Set default config path
CONFIG_PATH=${1:-"./custom-chat-config.json"}

# Check if config file exists
if [ ! -f "$CONFIG_PATH" ]; then
  echo "Error: Configuration file not found at $CONFIG_PATH"
  echo "You can create one by copying the sample: cp custom-chat-config.sample.json custom-chat-config.json"
  exit 1
fi

# Export the environment variable and build
echo "Building widget with configuration from: $CONFIG_PATH"
CHAT_CONFIG_PATH=$CONFIG_PATH npx vite build

echo "Build complete! The widget has been built with your custom configuration."
echo "Output files are available in the dist/ directory." 