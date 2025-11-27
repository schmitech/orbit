#!/bin/bash
#
# ORBIT Build Tarball Script
# --------------------------
# This script builds a distributable tarball package for the ORBIT project.
#
# USAGE:
#   ./build-tarball.sh [VERSION]
#
# ARGUMENTS:
#   VERSION   (optional) The version string to use for the package (default: 1.0.0)
#
# DESCRIPTION:
#   - Cleans previous build artifacts and prepares a fresh build directory structure.
#   - Copies all necessary server, CLI, configuration, and example files into the build directory.
#   - Checks for required dependencies (python3 >= 3.12, tar, git [optional]).
#   - Verifies the Python version is at least 3.12.
#   - Generates a metadata file with build and version information.
#   - Creates a tar.gz archive of the package in the dist/ directory.
#   - Verifies the tarball and generates a SHA256 checksum.
#
# OUTPUTS:
#   - dist/orbit-<VERSION>.tar.gz           # The distributable tarball
#   - dist/orbit-<VERSION>.tar.gz.sha256    # SHA256 checksum file
#   - build-<timestamp>.log                 # Build log file
#
# REQUIREMENTS:
#   - bash
#   - python3 (>= 3.12)
#   - tar
#   - git (optional, for build metadata)
#
# EXAMPLES:
#   ./build-tarball.sh
#   ./build-tarball.sh 0.2.0
#
# For more details, see the inline comments or contact the ORBIT maintainers.
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

# Function to check if required directories exist
check_required_directories() {
    local missing_dirs=()
    
    for dir in server bin install examples config; do
        if [ ! -d "$dir" ]; then
            missing_dirs+=("$dir")
        fi
    done
    
    if [ ${#missing_dirs[@]} -ne 0 ]; then
        echo "Error: Missing required directories: ${missing_dirs[*]}"
        echo "Please run this script from the project root directory."
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

# Check required directories
check_required_directories

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist
mkdir -p dist/build/${PACKAGE_NAME}

# Create directory structure
echo "Creating directory structure..."
mkdir -p dist/build/${PACKAGE_NAME}/{bin,server,install,logs,config,utils,prompts,models}

# Copy core server files (excluding tests directory)
echo "Copying server files..."
find server -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/tests/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy install files (excluding build-tarball.sh)
echo "Copying install files..."
find install -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" -not -name "build-tarball.sh" -not -path "*/install/default-config/*" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Skip docker files (not needed in installation package)
echo "Skipping docker files (excluded from installation package)..."

# Copy bin files (CLI tools)
echo "Copying CLI tools..."
find bin -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy default-conversational-adapter-prompt.txt to prompts (needed for creating API keys)
echo "Copying default-conversational-adapter-prompt.txt to prompts directory..."
if [ -f "examples/prompts/examples/default-conversational-adapter-prompt.txt" ]; then
    mkdir -p "dist/build/${PACKAGE_NAME}/prompts"
    cp "examples/prompts/examples/default-conversational-adapter-prompt.txt" "dist/build/${PACKAGE_NAME}/prompts/default-conversational-adapter-prompt.txt"
    echo "✅ default-conversational-adapter-prompt.txt copied to prompts successfully"
else
    echo "⚠️ Warning: examples/prompts/examples/default-conversational-adapter-prompt.txt not found"
fi

# Copy default-config files as config directory
echo "Copying default configuration files..."
if [ -d "install/default-config" ]; then
    find install/default-config -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
        # Remove 'install/default-config' prefix and replace with 'config'
        rel_path="${file#install/default-config/}"
        mkdir -p "dist/build/${PACKAGE_NAME}/config/$(dirname "$rel_path")"
        cp "$file" "dist/build/${PACKAGE_NAME}/config/$rel_path"
    done
    echo "✅ Default config files copied successfully"
else
    echo "⚠️ Warning: install/default-config directory not found, falling back to config directory"
    find config -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
        mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
        cp "$file" "dist/build/${PACKAGE_NAME}/$file"
    done
fi

# Verify config files were copied
echo "Verifying configuration files..."
if [ -d "dist/build/${PACKAGE_NAME}/config" ]; then
    echo "✅ Config directory created successfully"
    echo "📁 Config files:"
    ls -la dist/build/${PACKAGE_NAME}/config/
else
    echo "⚠️ Warning: Config directory not found in build"
fi

# Create .env file from env.example
echo "Creating .env from env.example..."
if [ -f "env.example" ]; then
    cp env.example dist/build/${PACKAGE_NAME}/.env
else
    echo "Warning: env.example not found, creating empty .env..."
    touch dist/build/${PACKAGE_NAME}/.env
fi

# Download and include granite4-1b model for quick start
echo "Downloading granite4:1b model for quick start..."
GGUF_MODELS_CONFIG="install/gguf-models.json"
MODEL_NAME="granite4-1b"
MODELS_DIR="models"

# Function to get model info from JSON config
get_model_info() {
    local model_name="$1"
    local config_file="$2"
    if [ ! -f "$config_file" ]; then
        return 1
    fi
    python3 -c "
import json
import sys
try:
    with open('$config_file', 'r') as f:
        config = json.load(f)
    if '$model_name' in config['models']:
        model_info = config['models']['$model_name']
        print(f\"{model_info['repo_id']}\")
        print(f\"{model_info['filename']}\")
    else:
        sys.exit(1)
except Exception as e:
    sys.exit(1)
"
}

if [ -f "$GGUF_MODELS_CONFIG" ]; then
    model_info=$(get_model_info "$MODEL_NAME" "$GGUF_MODELS_CONFIG")
    if [ $? -eq 0 ]; then
        repo_id=$(echo "$model_info" | head -n 1)
        filename=$(echo "$model_info" | tail -n 1)
        
        # Check if model already exists locally
        if [ ! -f "$MODELS_DIR/$filename" ]; then
            echo "Downloading $MODEL_NAME from $repo_id..."
            if python3 install/download_hf_gguf_model.py \
                --repo-id "$repo_id" \
                --filename "$filename" \
                --output-dir "$MODELS_DIR"; then
                echo "✅ $MODEL_NAME downloaded successfully"
            else
                echo "⚠️ Warning: Failed to download $MODEL_NAME, continuing without it"
            fi
        else
            echo "✅ $MODEL_NAME already exists locally"
        fi
        
        # Copy model to tarball if it exists
        if [ -f "$MODELS_DIR/$filename" ]; then
            echo "Copying $MODEL_NAME to tarball..."
            cp "$MODELS_DIR/$filename" "dist/build/${PACKAGE_NAME}/models/$filename"
            echo "✅ Model included in tarball: models/$filename"
        fi
    else
        echo "⚠️ Warning: $MODEL_NAME not found in $GGUF_MODELS_CONFIG"
    fi
else
    echo "⚠️ Warning: $GGUF_MODELS_CONFIG not found, skipping model download"
fi

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

# Make scripts executable
echo "Making scripts executable..."
chmod +x dist/build/${PACKAGE_NAME}/bin/orbit.py
chmod +x dist/build/${PACKAGE_NAME}/bin/orbit.sh
chmod +x dist/build/${PACKAGE_NAME}/install/setup.sh

# Create tarball
echo "Creating distribution tarball..."
cd dist/build
# Use --no-xattrs flag on macOS to exclude extended attributes for cross-platform compatibility
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - exclude extended attributes and resource fork files for Linux compatibility
    export COPYFILE_DISABLE=1
    tar --no-xattrs -czf ../${PACKAGE_NAME}.tar.gz ${PACKAGE_NAME}
    unset COPYFILE_DISABLE
else
    # Linux and others
    tar -czf ../${PACKAGE_NAME}.tar.gz ${PACKAGE_NAME}
fi
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