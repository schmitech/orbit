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

# 1.1. Ensure TypeScript declarations are generated
echo "Ensuring TypeScript declarations are generated..."
if [ ! -f "dist/index.d.ts" ]; then
    echo "TypeScript declarations missing, running tsc explicitly..."
    npx tsc --emitDeclarationOnly || {
        echo "Error: TypeScript declaration generation failed"
        exit 1
    }
fi

# 2. Create combined bundle
echo "Creating combined bundle..."
npm run build:bundle || {
    echo "Error: Bundle creation failed"
    exit 1
}

# Verify build outputs
echo "Verifying build outputs..."
REQUIRED_FILES=(
    "dist/chatbot-widget.umd.js"
    "dist/chatbot-widget.es.js" 
    "dist/chatbot-widget.bundle.js"
    "dist/chatbot-widget.css"
    "dist/index.d.ts"
    "dist/ChatWidget.d.ts"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -ne 0 ]; then
    echo "Error: Required build outputs are missing:"
    printf '%s\n' "${MISSING_FILES[@]}"
    exit 1
fi

# Additional verification for TypeScript declarations
echo "Verifying TypeScript declarations structure..."
if [ ! -d "dist/ui" ] || [ ! -d "dist/store" ] || [ ! -d "dist/hooks" ]; then
    echo "Warning: Some TypeScript declaration folders are missing"
    echo "Running TypeScript compilation again..."
    npx tsc --emitDeclarationOnly || {
        echo "Error: TypeScript declaration generation failed on retry"
        exit 1
    }
fi

# Final size and file count verification
echo "Final verification..."
TOTAL_FILES=$(find dist -type f | wc -l)
DIST_SIZE=$(du -sh dist | cut -f1)

echo "✅ Build completed successfully!"
echo "📦 Version: $VERSION"
echo "📁 Generated $TOTAL_FILES files in dist/ ($DIST_SIZE total)"
echo ""
echo "🚀 Ready for publishing! You can now:"
echo "   1. Test locally: Open demo.html in your browser"
echo "   2. Dry run: npm pack --dry-run"
echo "   3. Publish: npm publish --access public"
echo ""
echo "📋 Generated files:"
ls -la dist/ | grep -E '\.(js|css|d\.ts)$' | awk '{print "   " $9 " (" $5 " bytes)"}' 