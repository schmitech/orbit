#!/bin/bash
#
# ORBIT Docker Image Publishing Script
# -------------------------------------
# This script builds and publishes the ORBIT server Docker image.
# Uses docker-compose for orchestration with Ollama in a separate container.
#
# FEATURES:
#   - Automatic GPU/CPU detection at runtime
#   - Lean server-only image (no Ollama, no Node.js)
#   - Performance-optimized for both CPU and NVIDIA GPU
#
# USAGE:
#   ./publish.sh [OPTIONS]
#
# OPTIONS:
#   --build              Build the Docker image
#   --publish            Build and push to Docker Hub
#   --tag VERSION        Tag version (e.g., v1.0.0)
#   --help               Show this help message
#
# EXAMPLES:
#   ./publish.sh --build
#   ./publish.sh --publish
#   ./publish.sh --publish --tag v1.0.0
#
# RUNNING WITH DOCKER COMPOSE:
#   CPU mode:
#     cd docker && docker compose up -d
#
#   GPU mode (NVIDIA):
#     cd docker && docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
#
#   Connect orbitchat from host:
#     npm install -g orbitchat
#     ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat
#
set -euo pipefail

# Default values
BUILD=false
PUBLISH=false
NO_CACHE=false
VERSION_TAG=""
CUDA_VER="cu121"
UID_ARG="1001"
GID_ARG="0"
IMAGE_NAME="schmitech/orbit"
IMAGE_TAG_BASIC="basic"
IMAGE_TAG_LATEST="latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Change to project root (one level up from docker/)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

print_help() {
    echo "Usage: ./publish.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build              Build the Docker image"
    echo "  --publish            Build and push to Docker Hub"
    echo "  --tag VERSION        Tag version (e.g., v1.0.0)"
    echo "  --cuda-ver VER       CUDA wheel channel (default: cu121, e.g. cu124, cu128)"
    echo "  --uid UID            User ID for the orbit process (default: 1001)"
    echo "  --gid GID            Group ID for the orbit process (default: 0)"
    echo "  --no-cache           Build without using Docker layer cache"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./publish.sh --build"
    echo "  ./publish.sh --build --no-cache"
    echo "  ./publish.sh --publish --tag v1.0.0"
    echo "  ./publish.sh --publish --cuda-ver cu128 --tag v1.0.0"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --publish) PUBLISH=true; BUILD=true; shift ;;
        --no-cache) NO_CACHE=true; shift ;;
        --tag) VERSION_TAG="$2"; shift 2 ;;
        --cuda-ver) CUDA_VER="$2"; shift 2 ;;
        --uid) UID_ARG="$2"; shift 2 ;;
        --gid) GID_ARG="$2"; shift 2 ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Change to project root
cd "$PROJECT_ROOT"

# Verify required files exist
if [ ! -f "docker/Dockerfile" ]; then
    echo -e "${RED}docker/Dockerfile not found${NC}"
    exit 1
fi

if [ ! -f "install/default-config/ollama.yaml" ]; then
    echo -e "${RED}install/default-config/ollama.yaml not found${NC}"
    exit 1
fi

if [ ! -f "install/default-config/inference.yaml" ]; then
    echo -e "${RED}install/default-config/inference.yaml not found${NC}"
    exit 1
fi

if [ ! -f "install/orbit.db.default" ]; then
    echo -e "${RED}install/orbit.db.default not found${NC}"
    exit 1
fi

# Build the image
if [ "$BUILD" = true ]; then
    echo -e "${BLUE}Building ORBIT server Docker image...${NC}"

    echo -e "${GREEN}Configuration:${NC}"
    echo -e "${BLUE}   Image: Server-only (Ollama runs separately via docker-compose)${NC}"
    echo -e "${BLUE}   Presets: smollm2-1.7b-cpu / smollm2-1.7b-gpu (auto-detected)${NC}"
    echo -e "${BLUE}   CUDA wheel channel: ${CUDA_VER}${NC}"
    echo -e "${BLUE}   UID/GID: ${UID_ARG}/${GID_ARG}${NC}"
    echo -e "${GREEN}Hardware Support:${NC}"
    echo -e "${BLUE}   CPU: Optimized with OpenBLAS${NC}"
    echo -e "${BLUE}   GPU: NVIDIA CUDA (use docker-compose.gpu.yml override)${NC}"

    # Verify default database exists
    if [ -f "install/orbit.db.default" ]; then
        db_size=$(du -h "install/orbit.db.default" | cut -f1)
        echo -e "${GREEN}Default database found: install/orbit.db.default (${db_size})${NC}"
    fi

    # Build the Docker image
    echo -e "${YELLOW}Building Docker image...${NC}"

    BUILD_ARGS=(
        --build-arg "CUDA_VER=${CUDA_VER}"
        --build-arg "UID=${UID_ARG}"
        --build-arg "GID=${GID_ARG}"
    )
    if [ "$NO_CACHE" = true ]; then
        BUILD_ARGS+=(--no-cache)
    fi

    if docker build \
        -f docker/Dockerfile \
        "${BUILD_ARGS[@]}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG_LATEST}" \
        .; then
        echo -e "${GREEN}Docker image built successfully${NC}"

        # Show image info
        echo -e "${BLUE}Image information:${NC}"
        docker images "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    else
        echo -e "${RED}Failed to build Docker image${NC}"
        exit 1
    fi

    # Add version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}Tagging image with version: $VERSION_TAG${NC}"
        docker tag "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
        echo -e "${GREEN}Tagged as ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
    fi
fi

# Publish the image
if [ "$PUBLISH" = true ]; then
    echo -e "${BLUE}Publishing Docker image to Docker Hub...${NC}"

    # Push basic tag
    echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}...${NC}"
    if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}"; then
        echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
    else
        echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
        exit 1
    fi

    # Push latest tag
    echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_LATEST}...${NC}"
    if docker push "${IMAGE_NAME}:${IMAGE_TAG_LATEST}"; then
        echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
    else
        echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
        exit 1
    fi

    # Push version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}...${NC}"
        if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"; then
            echo -e "${GREEN}Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
        else
            echo -e "${RED}Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}Successfully published ORBIT server image to Docker Hub!${NC}"
    echo -e "${BLUE}Published tags:${NC}"
    echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
    echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_LATEST}"
    if [ -n "$VERSION_TAG" ]; then
        echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
    fi
    echo ""
    echo -e "${BLUE}Run with docker compose:${NC}"
    echo -e "   cd docker && docker compose up -d"
    echo ""
    echo -e "${BLUE}GPU mode (NVIDIA):${NC}"
    echo -e "   cd docker && docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d"
    echo ""
    echo -e "${BLUE}Connect orbitchat from host:${NC}"
    echo -e "   npm install -g orbitchat"
    echo -e "   ORBIT_ADAPTER_KEYS='{\"simple-chat\":\"default-key\"}' orbitchat"
fi

echo -e "${GREEN}Done!${NC}"
