#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  @schmitech/markdown-renderer Test Suite  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"
echo ""

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 Installing dependencies...${NC}"
    npm install
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to install dependencies${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Dependencies installed${NC}"
    echo ""
fi

# Check if dist folder exists (for built package test)
if [ "$1" == "--build" ]; then
    echo -e "${YELLOW}🔨 Building package...${NC}"
    npm run build
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Build failed${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Package built successfully${NC}"
    echo ""
    
    # Check dist contents
    echo -e "${BLUE}📁 Checking dist folder contents:${NC}"
    if [ -f "dist/markdown-renderer.es.js" ]; then
        echo -e "${GREEN}  ✓ ES module found${NC}"
    else
        echo -e "${RED}  ✗ ES module missing${NC}"
    fi
    
    if [ -f "dist/markdown-renderer.umd.js" ]; then
        echo -e "${GREEN}  ✓ UMD module found${NC}"
    else
        echo -e "${RED}  ✗ UMD module missing${NC}"
    fi
    
    if [ -f "dist/index.d.ts" ]; then
        echo -e "${GREEN}  ✓ TypeScript definitions found${NC}"
    else
        echo -e "${RED}  ✗ TypeScript definitions missing${NC}"
    fi
    
    if [ -f "dist/MarkdownStyles.css" ]; then
        echo -e "${GREEN}  ✓ CSS styles found${NC}"
    else
        echo -e "${RED}  ✗ CSS styles missing${NC}"
    fi
    echo ""
    
    echo -e "${BLUE}🚀 Starting test server with built package...${NC}"
    echo -e "${YELLOW}   Opening http://localhost:3334${NC}"
    echo ""
    npm run test:build
else
    echo -e "${BLUE}🚀 Starting development test server...${NC}"
    echo -e "${YELLOW}   Opening http://localhost:3333${NC}"
    echo ""
    echo -e "${GREEN}Test Instructions:${NC}"
    echo "  1. Test all markdown features in the sidebar"
    echo "  2. Try the custom input with your own markdown"
    echo "  3. Run the stress test to check performance"
    echo "  4. Check the sample integration for real-world usage"
    echo ""
    echo -e "${YELLOW}Tip: Run './test.sh --build' to test the built package${NC}"
    echo ""
    npm run test
fi