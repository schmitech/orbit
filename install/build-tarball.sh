#!/bin/bash
set -e

# Parse command line arguments
VERSION=${1:-"1.0.0"}  # Use first argument or default to 1.0.0
PACKAGE_NAME="orbit-${VERSION}"

# Set up logging
LOG_FILE="build-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "Build started at $(date)"
echo "Logging to $LOG_FILE"
echo "Building version: ${VERSION}"

# Function to check Python version
check_python_version() {
    local python_cmd=$1
    local version=$($python_cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 12 ]); then
        echo "Error: Python 3.12 or higher is required (detected $version)"
        exit 1
    fi
    echo "Found Python $version"
}

# Function to check required commands
check_requirements() {
    local missing_deps=()
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        check_python_version python3
    fi
    
    # Check tar
    if ! command -v tar &> /dev/null; then
        missing_deps+=("tar")
    fi
    
    # Check git (optional)
    if ! command -v git &> /dev/null; then
        echo "Warning: git not found. Version information may be incomplete."
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "Error: Missing required dependencies: ${missing_deps[*]}"
        exit 1
    fi
}

# Function to clean up on exit
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "Error: Build failed with exit code $exit_code"
        rm -rf dist/build
    fi
    exit $exit_code
}

# Function to show progress
show_progress() {
    local pid=$1
    local message=$2
    echo -n "$message"
    while kill -0 $pid 2>/dev/null; do
        echo -n "."
        sleep 1
    done
    echo " done!"
}

# Set up cleanup trap
trap cleanup EXIT

echo "Building ORBIT distributable package v${VERSION}..."

# Check requirements
check_requirements

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist
mkdir -p dist/build/${PACKAGE_NAME}

# Create directory structure
echo "Creating directory structure..."
mkdir -p dist/build/${PACKAGE_NAME}/{bin,server,prompts,docs,logs,sample_db}

# Copy core server files
echo "Copying server files..."
find server -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy bin files (CLI tools)
echo "Copying CLI tools..."
find bin -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy utils directory (sample data and tools)
echo "Copying sample databases and scripts..."
find sample_db -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy utils directory (sample data and tools)
echo "Copying prompts..."
find prompts -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy configuration files
echo "Copying configuration files..."
cp install/dependencies.toml dist/build/${PACKAGE_NAME}/ 2>/dev/null || echo "Warning: dependencies.toml not found"
cp README.md dist/build/${PACKAGE_NAME}/ 2>/dev/null || echo "Warning: README.md not found"
chmod +x install/setup.sh
cp install/setup.sh dist/build/${PACKAGE_NAME}/ 2>/dev/null || echo "Warning: setup.sh not found"


# Create example configuration
echo "Creating example configuration yaml file..."
cp config.yaml.example dist/build/${PACKAGE_NAME}/config.yaml

# Create .env.example file
echo "Creating .env.example..."
cp .env.example dist/build/${PACKAGE_NAME}/.env.example

# Create metadata file
echo "Creating metadata file..."
cat > dist/build/${PACKAGE_NAME}/meta.json << EOF
{
  "name": "ORBIT",
  "version": "${VERSION}",
  "description": "Open Retrieval-Based Inference Toolkit",
  "date": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "build": "$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')",
  "python_version": "$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
}
EOF

# Create installation and setup script
echo "Creating installation script..."
cp install/install.sh.template dist/build/${PACKAGE_NAME}/install.sh
chmod +x dist/build/${PACKAGE_NAME}/install.sh

# Create documentation
echo "Creating documentation..."
cat > dist/build/${PACKAGE_NAME}/docs/QUICKSTART.md << 'EOF'
# ORBIT Quick Start Guide

This guide will help you get started with ORBIT server and CLI.

## Prerequisites

- Python 3.12 or higher
- MongoDB (for API key management and system prompts)
- Ollama (optional, for local LLM inference)

## Installation

1. Extract the ORBIT package:
   ```
   tar -xzf orbit-0.1.0.tar.gz
   cd orbit-0.1.0
   ```

2. Run the installation script:
   ```
   ./install.sh
   ```

3. Configure your environment:
   - Edit `.env` to set your API keys
   - Edit `config/config.yaml` to configure the server

## Starting the Server

```
orbit start
```

For development mode with auto-reload:
```
orbit start --reload
```
EOF

# Make scripts executable
echo "Making scripts executable..."
chmod +x dist/build/${PACKAGE_NAME}/bin/orbit.py
chmod +x dist/build/${PACKAGE_NAME}/bin/orbit.sh
chmod +x dist/build/${PACKAGE_NAME}/setup.sh
chmod +x dist/build/${PACKAGE_NAME}/sample_db/sample-db-setup.sh

# Create tarball
echo "Creating distribution tarball..."
cd dist/build
tar -czf ../${PACKAGE_NAME}.tar.gz ${PACKAGE_NAME}
cd ../..

# Verify the tarball
echo "Verifying tarball..."
if [ -f "dist/${PACKAGE_NAME}.tar.gz" ]; then
    echo "✅ Tarball created successfully: dist/${PACKAGE_NAME}.tar.gz"
    echo "Size: $(du -h dist/${PACKAGE_NAME}.tar.gz | cut -f1)"
    
    # List contents of the tarball
    echo "Contents:"
    tar -tvf dist/${PACKAGE_NAME}.tar.gz | head -n 10
    echo "..."
    
    # Check for __pycache__ directories in the tarball
    echo "Verifying no __pycache__ directories in the tarball..."
    PYCACHE_COUNT=$(tar -tvf dist/${PACKAGE_NAME}.tar.gz | grep "__pycache__" | wc -l)
    if [ "$PYCACHE_COUNT" -eq 0 ]; then
        echo "✅ No __pycache__ directories found in tarball"
    else
        echo "⚠️ Warning: Found $PYCACHE_COUNT __pycache__ directories in tarball"
    fi
    
    # Generate checksum
    echo "Generating SHA256 checksum..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        shasum -a 256 "dist/${PACKAGE_NAME}.tar.gz" > "dist/${PACKAGE_NAME}.tar.gz.sha256"
    else
        # Linux and others
        sha256sum "dist/${PACKAGE_NAME}.tar.gz" > "dist/${PACKAGE_NAME}.tar.gz.sha256"
    fi
    echo "Checksum saved to: dist/${PACKAGE_NAME}.tar.gz.sha256"
    echo "SHA256: $(cat dist/${PACKAGE_NAME}.tar.gz.sha256 | cut -d' ' -f1)"
else
    echo "❌ Error: Failed to create tarball"
    exit 1
fi

echo "Build completed successfully!"