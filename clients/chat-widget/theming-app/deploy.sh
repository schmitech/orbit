#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting local deployment...${NC}\n"

# Check if widget dist files exist
if [ ! -f "../dist/chatbot-widget.umd.js" ] || [ ! -f "../dist/chatbot-widget.css" ]; then
    echo -e "❌ Widget dist files not found!"
    echo -e "💡 Please run: cd ../.. && npm run build"
    exit 1
fi

# Create public/dist directory if it doesn't exist
mkdir -p public/dist

# Copy widget files
echo -e "${BLUE}📦 Copying widget files to public directory...${NC}"
cp ../dist/chatbot-widget.umd.js public/dist/
cp ../dist/chatbot-widget.css public/dist/

# Get file sizes
JS_SIZE=$(du -h public/dist/chatbot-widget.umd.js | cut -f1)
CSS_SIZE=$(du -h public/dist/chatbot-widget.css | cut -f1)

echo -e "\n${GREEN}✅ Files copied successfully:${NC}"
echo -e "   - chatbot-widget.umd.js (${JS_SIZE})"
echo -e "   - chatbot-widget.css (${CSS_SIZE})"

# Ensure .env.local is configured correctly
echo -e "\n${BLUE}🔧 Checking environment configuration...${NC}"

# Create or update .env.local
cat > .env.local << EOF
VITE_WIDGET_SOURCE=npm
VITE_LOCAL_WIDGET_JS_PATH=/dist/chatbot-widget.umd.js
VITE_LOCAL_WIDGET_CSS_PATH=/dist/chatbot-widget.css
VITE_NPM_WIDGET_VERSION=0.4.19
VITE_WIDGET_DEBUG=false
VITE_PROMPT_ENABLED=false
VITE_DEFAULT_API_ENDPOINT=http://localhost:3000
VITE_GITHUB_OWNER=schmitech
VITE_GITHUB_REPO=orbit
VITE_UNAVAILABLE_MSG=false
EOF

echo -e "${GREEN}✅ Environment configured${NC}"

# Start development server
echo -e "\n${BLUE}🚀 Starting development server...${NC}"
npm run dev:local 