#!/bin/bash

# Deploy script for Orbit Chat App
# This script builds and deploys the app to Netlify
#
# PREREQUISITES:
# 1. Install Netlify CLI: npm install -g netlify-cli
# 2. Login to Netlify: netlify login
# 3. Initialize Netlify in this directory: netlify init
# 4. Ensure you have a .env file with required environment variables
#
# USAGE: ./deploy.sh

set -e  # Exit on any error

echo "🚀 Starting deployment process..."
echo ""
echo "📋 Checking prerequisites..."

# Check if netlify CLI is installed
if ! command -v netlify &> /dev/null; then
    echo "❌ Error: Netlify CLI not found."
    echo "   Please install it with: npm install -g netlify-cli"
    echo "   Then run: netlify login"
    echo "   Then run: netlify init"
    exit 1
fi

# Check if user is logged in to Netlify
if ! netlify status &> /dev/null; then
    echo "❌ Error: Not logged in to Netlify."
    echo "   Please run: netlify login"
    echo "   Then run: netlify init"
    exit 1
fi

# Check if Netlify is initialized (look for .netlify directory)
if [ ! -d ".netlify" ]; then
    echo "❌ Error: Netlify not initialized in this directory."
    echo "   Please run: netlify init"
    echo "   Follow the prompts to connect to an existing site or create a new one"
    exit 1
fi

echo "✅ Prerequisites check passed!"
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found. Please run this script from the chat-app directory."
    exit 1
fi

# Check if netlify CLI is installed
if ! command -v netlify &> /dev/null; then
    echo "❌ Error: Netlify CLI not found. Please install it with: npm install -g netlify-cli"
    exit 1
fi

# Build the project
echo "📦 Building the project..."
npm run build

# Check if dist directory exists and has content
if [ ! -d "dist" ] || [ -z "$(ls -A dist)" ]; then
    echo "❌ Error: dist directory is empty or doesn't exist. Build failed."
    exit 1
fi

echo "✅ Build completed successfully!"

# Deploy to Netlify
echo "🌐 Deploying to Netlify..."
netlify deploy --prod --dir=dist

echo "🎉 Deployment completed successfully!"
echo "Your app is now live at: https://app-name.netlify.app"

