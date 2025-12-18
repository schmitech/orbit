#!/bin/bash

# ============================================================================
# Chat Widget Build Script
# ============================================================================
# 
# PURPOSE:
#   Builds the @schmitech/chatbot-widget package for distribution.
#   Supports both production builds (using npm package dependencies) and
#   development builds (using local node-api for testing).
#
# USAGE:
#   ./build.sh                  # Production build (publishable to npm)
#   ./build.sh --use-local-api  # Development build (uses local ../node-api)
#   ./build.sh --help           # Show help message
#
# WHAT IT DOES:
#   1. Verifies prerequisites (npm, node)
#   2. Optionally configures build to use local API (--use-local-api flag)
#   3. Runs TypeScript compilation and Vite build
#   4. Creates UMD, ES, and bundle versions
#   5. Generates TypeScript declarations
#   6. Verifies all required outputs exist
#   7. Restores original configuration if local API was used
#
# OUTPUT:
#   dist/
#   ├── chatbot-widget.umd.js      # UMD bundle for script tags
#   ├── chatbot-widget.es.js       # ES module for modern bundlers
#   ├── chatbot-widget.bundle.js   # Combined bundle with all dependencies
#   ├── chatbot-widget.css         # Compiled styles
#   └── *.d.ts                     # TypeScript declarations
#
# LOCAL API TESTING:
#   The --use-local-api flag allows testing changes to ../node-api before
#   publishing a new npm package. This flag:
#   - First builds the local node-api to ensure dist files are current
#   - Temporarily modifies package.json and vite.config.ts
#   - Points to ../node-api/dist/api.mjs (the compiled version)
#   - Builds the widget using the local API dist files
#   - Restores original files after build
#   - Shows warning not to publish the resulting build
#
# REQUIREMENTS:
#   - Node.js and npm installed
#   - Run from the chat-widget directory
#   - For --use-local-api: ../node-api directory must exist
#
# ============================================================================

# Exit on any error
set -e

# Cleanup function to restore original files
cleanup() {
    if [ "$USE_LOCAL_API" = true ]; then
        if [ -n "$PACKAGE_JSON_BACKUP" ] && [ -f "$PACKAGE_JSON_BACKUP" ]; then
            cp "$PACKAGE_JSON_BACKUP" package.json
            rm -f "$PACKAGE_JSON_BACKUP"
            echo "Restored original package.json"
        fi
        if [ -n "$VITE_CONFIG_BACKUP" ] && [ -f "$VITE_CONFIG_BACKUP" ]; then
            cp "$VITE_CONFIG_BACKUP" vite.config.ts
            rm -f "$VITE_CONFIG_BACKUP"
            echo "Restored original vite.config.ts"
        fi
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Parse command line arguments
USE_LOCAL_API=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --use-local-api)
            USE_LOCAL_API=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Build the chatbot widget package"
            echo ""
            echo "Options:"
            echo "  --use-local-api    Use local node-api (../node-api) instead of npm package"
            echo "                     for testing before publishing. DO NOT publish builds"
            echo "                     created with this flag!"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                 # Build with npm package (for publishing)"
            echo "  $0 --use-local-api # Build with local API (for testing)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--use-local-api] [-h|--help]"
            echo "Run '$0 --help' for more information"
            exit 1
            ;;
    esac
done

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

# Handle local API usage
PACKAGE_JSON_BACKUP=""
VITE_CONFIG_BACKUP=""
if [ "$USE_LOCAL_API" = true ]; then
    echo "🔗 Using local node-api instead of npm package..."
    
    # Create backup of package.json
    PACKAGE_JSON_BACKUP=$(mktemp)
    cp package.json "$PACKAGE_JSON_BACKUP"
    
    # Create backup of vite.config.ts
    VITE_CONFIG_BACKUP=$(mktemp)
    cp vite.config.ts "$VITE_CONFIG_BACKUP"
    
    # Update package.json to use local api with file: protocol
    node -e "
        const fs = require('fs');
        const path = require('path');
        const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
        pkg.dependencies['@schmitech/chatbot-api'] = 'file:../node-api';
        fs.writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\\n');
        console.log('Updated package.json to use local node-api');
    "
    
    # Build the local node-api first to ensure dist files exist
    echo "📦 Building local node-api to ensure dist files are up-to-date..."
    (cd ../node-api && npm run build) || {
        echo "Error: Failed to build local node-api"
        # Restore files on error
        [ -n "$PACKAGE_JSON_BACKUP" ] && cp "$PACKAGE_JSON_BACKUP" package.json
        [ -n "$VITE_CONFIG_BACKUP" ] && cp "$VITE_CONFIG_BACKUP" vite.config.ts
        exit 1
    }
    
    # Create a temporary vite config that aliases the import to the built dist files
    cat > vite.config.ts << 'EOF'
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    svgr()
  ],
  resolve: {
    alias: {
      '@schmitech/chatbot-api': path.resolve(__dirname, '../node-api/dist/api.mjs')
    }
  },
  define: {
    'process.env': '{}',
    'global': '{}'
  },
  build: {
    lib: {
      entry: 'src/index.ts',
      formats: ['es', 'umd'],
      name: 'ChatbotWidget',
      fileName: (format) => `chatbot-widget.${format}.js`
    },
    rollupOptions: {
      external: ['react', 'react-dom'],
      output: {
        exports: 'named',
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM'
        },
        assetFileNames: 'chatbot-widget.css',
        intro: 'if (typeof window !== "undefined") { window.global = window; }',
      }
    },
    cssCodeSplit: false,
    cssTarget: 'chrome61'
  },
  optimizeDeps: {
    exclude: ['lucide-react']
  }
});
EOF
    
    echo "📦 Installing dependencies with local API..."
    npm install || {
        echo "Error: npm install failed"
        # Restore files on error
        [ -n "$PACKAGE_JSON_BACKUP" ] && cp "$PACKAGE_JSON_BACKUP" package.json
        [ -n "$VITE_CONFIG_BACKUP" ] && cp "$VITE_CONFIG_BACKUP" vite.config.ts
        exit 1
    }
fi

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

# Display appropriate message based on build type
if [ "$USE_LOCAL_API" = true ]; then
    echo ""
    echo "⚠️  Note: This build used the local node-api for testing."
    echo "   Do NOT publish this build to npm!"
    echo "   Run without --use-local-api flag to create a publishable build."
else
    echo ""
    echo "🚀 Ready for publishing! You can now:"
    echo "   1. Dry run: npm pack --dry-run"
    echo "   2. Publish: npm publish --access public"
fi

echo ""
echo "📋 Generated files:"
ls -la dist/ | grep -E '\.(js|css|d\.ts)$' | awk '{print "   " $9 " (" $5 " bytes)"}' 