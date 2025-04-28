#!/bin/bash

echo "Starting chatbot widget build process..."

# 1. Create directories if they don't exist
echo "Creating public/libs directory..."
mkdir -p public/libs

# 2. Build the widget
echo "Building widget..."
npm run build

# 3. Copy React dependencies
echo "Copying React libraries..."
cp node_modules/react/umd/react.production.min.js public/libs/
cp node_modules/react-dom/umd/react-dom.production.min.js public/libs/

# 4. Optional: Create combined bundle
echo "Creating combined bundle..."
npm run build:bundle

echo "Build completed successfully!"
echo "You can now open demo.html in your browser to test the widget." 