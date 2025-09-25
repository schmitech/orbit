#!/bin/bash

# Test script for local API functionality
# This script demonstrates how to test the chat-app with local API dist

echo "🚀 Testing Local API Integration"
echo "================================"

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: Please run this script from the chat-app directory"
    exit 1
fi

# Check if node-api dist exists
if [ ! -d "../node-api/dist" ]; then
    echo "📦 Building node-api first..."
    cd ../node-api
    npm run build
    if [ $? -ne 0 ]; then
        echo "❌ Failed to build node-api"
        exit 1
    fi
    cd ../chat-app
    echo "✅ node-api built successfully"
fi

# Copy dist files to public directory for local testing
echo "📁 Copying API dist to public directory..."
mkdir -p public/api
cp -r ../node-api/dist/* public/api/
echo "✅ API files copied to public directory"

# Create .env.local file for local testing
echo "🔧 Setting up environment for local API testing..."
cat > .env.local << EOF
VITE_API_URL=http://localhost:3000
VITE_API_KEY=chat-key
VITE_ENABLE_UPLOAD_BUTTON=false
VITE_USE_LOCAL_API=true
VITE_LOCAL_API_PATH=/api
EOF

echo "✅ Environment configured for local API"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

echo ""
echo "🎯 Available commands:"
echo "  npm run dev:local     - Start dev server with local API"
echo "  npm run dev:with-api  - Build API and start with local API"
echo "  npm run build:local   - Build app with local API"
echo ""
echo "🌐 To test with npm package instead:"
echo "  Set VITE_USE_LOCAL_API=false in .env.local"
echo "  npm run dev"
echo ""
echo "✨ Ready to test! Run 'npm run dev:local' to start"
