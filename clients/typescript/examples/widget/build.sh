#!/bin/bash

# Exit on any error
set -e

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check for required commands
echo "Checking prerequisites..."
if ! command_exists npm; then
    echo "Error: npm is not installed"
    exit 1
fi

if ! command_exists node; then
    echo "Error: node is not installed"
    exit 1
fi

echo "Starting chatbot widget build process..."

# Get current version from package.json
VERSION=$(node -p "require('./package.json').version")
echo "Building version: $VERSION"

echo "Removing dist directory..."
rm -rf dist

# 1. Build the widget
echo "Building widget..."
npm run build || {
    echo "Error: Widget build failed"
    exit 1
}

# 2. Create combined bundle
echo "Creating combined bundle..."
npm run build:bundle || {
    echo "Error: Bundle creation failed"
    exit 1
}

# Verify build outputs
echo "Verifying build outputs..."
if [ ! -f "dist/chatbot-widget.umd.js" ] || [ ! -f "dist/chatbot-widget.es.js" ] || [ ! -f "dist/chatbot-widget.bundle.js" ]; then
    echo "Error: Some build outputs are missing"
    exit 1
fi

echo "Build completed successfully!"
echo "Version: $VERSION"
echo "You can now:"
echo "1. Open demo.html in your browser to test the widget"
echo "2. Run 'npm pack --dry-run' to test the package"
echo "3. Run 'npm publish --access public' to publish" 