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
    
    for dir in server bin install docker examples; do
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
mkdir -p dist/build/${PACKAGE_NAME}/{bin,server,install,logs,examples,docker}

# Copy core server files (excluding tests directory)
echo "Copying server files..."
find server -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/tests/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy install files (excluding build-tarball.sh)
echo "Copying install files..."
find install -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" -not -name "build-tarball.sh" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy docker files
echo "Copying docker files..."
find docker -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Copy bin files (CLI tools)
echo "Copying CLI tools..."
find bin -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Sample data and scripts
echo "Copying sample databases and scripts..."
find examples -type f -not -path "*/\.*" -not -path "*/__pycache__/*" -not -name "*.pyc" -not -name "*.pyo" -not -name "*.pyd" | while read file; do
    mkdir -p "dist/build/${PACKAGE_NAME}/$(dirname "$file")"
    cp "$file" "dist/build/${PACKAGE_NAME}/$file"
done

# Create example configuration
echo "Creating example configuration yaml file..."
if [ -f "config.yaml.example" ]; then
    cp config.yaml.example dist/build/${PACKAGE_NAME}/config.yaml
else
    echo "Warning: config.yaml.example not found, creating empty config.yaml..."
    touch dist/build/${PACKAGE_NAME}/config.yaml
fi

# Create .env.example file
echo "Creating .env.example..."
if [ -f ".env.example" ]; then
    cp .env.example dist/build/${PACKAGE_NAME}/.env.example
else
    echo "Warning: .env.example not found, creating empty .env.example..."
    touch dist/build/${PACKAGE_NAME}/.env.example
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
chmod +x dist/build/${PACKAGE_NAME}/examples/sample-db-setup.sh

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