#!/bin/bash

# =============================================================================
# ORBIT Chatbot Widget Theming Platform - Deployment Script
# =============================================================================
#
# This script deploys the theming platform in either local development or 
# NPM production mode, automatically configuring the environment variables
# and copying necessary files.
#
# USAGE:
#   ./deploy.sh [mode]
#
# ARGUMENTS:
#   mode    Optional. Specify deployment mode:
#           - local  (default) - Use local widget build for development
#           - npm             - Use NPM package for production
#
# EXAMPLES:
#   ./deploy.sh              # Deploy in local mode (default)
#   ./deploy.sh local        # Deploy in local mode (explicit)
#   ./deploy.sh npm          # Deploy in NPM mode
#
# LOCAL MODE:
#   - Requires ../dist/chatbot-widget.umd.js and ../dist/chatbot-widget.css
#   - Copies widget files to public/dist/
#   - Enables endpoint field editing (VITE_ENDPOINT_FIELD_ENABLED=true)
#   - Enables debug mode (VITE_WIDGET_DEBUG=true)
#   - Uses local widget source (VITE_WIDGET_SOURCE=local)
#   - Runs: npm run dev:local
#
# NPM MODE:
#   - Uses @schmitech/chatbot-widget NPM package
#   - Disables endpoint field editing (VITE_ENDPOINT_FIELD_ENABLED=false)
#   - Disables debug mode (VITE_WIDGET_DEBUG=false)
#   - Uses NPM widget source (VITE_WIDGET_SOURCE=npm)
#   - Runs: npm run dev:npm
#
# PREREQUISITES:
#   - Node.js and npm installed
#   - For local mode: Widget must be built (run: cd ../.. && npm run build)
#   - For NPM mode: @schmitech/chatbot-widget package installed
#
# ENVIRONMENT FILES:
#   - Creates/updates .env.local with appropriate configuration
#   - See env.example for all available environment variables
#
# =============================================================================

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default to local if no argument provided
MODE=${1:-local}

# Validate mode argument
if [[ "$MODE" != "local" && "$MODE" != "npm" ]]; then
    echo -e "${RED}❌ Invalid mode. Please use 'local' or 'npm'${NC}"
    echo -e "${YELLOW}Usage: $0 [local|npm]${NC}"
    echo -e "  local: Use local widget build (requires ../dist/ files)"
    echo -e "  npm:   Use NPM package"
    exit 1
fi

echo -e "${BLUE}🚀 Starting ${MODE} deployment...${NC}\n"

# Handle local mode - copy widget files
if [ "$MODE" = "local" ]; then
    # Check if widget dist files exist
    if [ ! -f "../dist/chatbot-widget.umd.js" ] || [ ! -f "../dist/chatbot-widget.css" ]; then
        echo -e "${RED}❌ Widget dist files not found!${NC}"
        echo -e "${YELLOW}💡 Please run: cd ../.. && npm run build${NC}"
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
else
    echo -e "${GREEN}✅ Using NPM package mode - no local files needed${NC}"
fi

# Ensure .env.local is configured correctly
echo -e "\n${BLUE}🔧 Configuring environment for ${MODE} mode...${NC}"

# Set environment variables based on mode
if [ "$MODE" = "local" ]; then
    WIDGET_SOURCE="local"
    ENDPOINT_FIELD_ENABLED="true"
    WIDGET_DEBUG="true"
    DEV_COMMAND="npm run dev:local"
else
    WIDGET_SOURCE="npm"
    ENDPOINT_FIELD_ENABLED="true"
    WIDGET_DEBUG="false"
    DEV_COMMAND="npm run dev:npm"
fi

# Create or update .env.local
cat > .env.local << EOF
VITE_WIDGET_SOURCE=${WIDGET_SOURCE}
VITE_LOCAL_WIDGET_JS_PATH=/dist/chatbot-widget.umd.js
VITE_LOCAL_WIDGET_CSS_PATH=/dist/chatbot-widget.css
VITE_NPM_WIDGET_VERSION=0.6.3
VITE_WIDGET_DEBUG=${WIDGET_DEBUG}
VITE_PROMPT_ENABLED=false
VITE_DEFAULT_API_ENDPOINT=http://localhost:3000
VITE_GITHUB_OWNER=schmitech
VITE_GITHUB_REPO=orbit
VITE_UNAVAILABLE_MSG=false
VITE_ENDPOINT_FIELD_ENABLED=${ENDPOINT_FIELD_ENABLED}
EOF

echo -e "${GREEN}✅ Environment configured for ${MODE} mode${NC}"
echo -e "   - Widget Source: ${WIDGET_SOURCE}"
echo -e "   - Endpoint Field: ${ENDPOINT_FIELD_ENABLED}"
echo -e "   - Debug Mode: ${WIDGET_DEBUG}"

# Start development server
echo -e "\n${BLUE}🚀 Starting development server...${NC}"
echo -e "${YELLOW}Running: ${DEV_COMMAND}${NC}"
${DEV_COMMAND} 