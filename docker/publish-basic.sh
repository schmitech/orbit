#!/bin/bash
#
# ORBIT Basic Docker Image Publishing Script
# -------------------------------------------
# This script builds and publishes a minimal ORBIT Docker image containing
# only the simple-chat adapter using Ollama with the granite4:1b model.
#
# USAGE:
#   ./publish-basic.sh [OPTIONS]
#
# OPTIONS:
#   --build              Build the Docker image
#   --publish            Build and push to Docker Hub
#   --tag VERSION        Tag version (e.g., v1.0.0)
#   --help               Show this help message
#
# EXAMPLES:
#   ./publish-basic.sh --build
#   ./publish-basic.sh --publish
#   ./publish-basic.sh --publish --tag v1.0.0
#
set -e

# Default values
BUILD=false
PUBLISH=false
VERSION_TAG=""
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
    echo "Usage: ./publish-basic.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build              Build the Docker image"
    echo "  --publish            Build and push to Docker Hub"
    echo "  --tag VERSION        Tag version (e.g., v1.0.0)"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./publish-basic.sh --build"
    echo "  ./publish-basic.sh --publish"
    echo "  ./publish-basic.sh --publish --tag v1.0.0"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --publish) PUBLISH=true; BUILD=true; shift ;;
        --tag)
            VERSION_TAG="$2"
            shift 2
            ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if user is logged into Docker Hub (only if publishing)
if [ "$PUBLISH" = true ]; then
    if ! docker info | grep -q "Username"; then
        echo -e "${YELLOW}⚠️  Not logged into Docker Hub. Attempting to login...${NC}"
        if ! docker login; then
            echo -e "${RED}❌ Failed to login to Docker Hub. Please login manually: docker login${NC}"
            exit 1
        fi
    fi
fi


# Change to project root
cd "$PROJECT_ROOT"

# Verify required files exist
if [ ! -f "docker/Dockerfile.basic" ]; then
    echo -e "${RED}❌ docker/Dockerfile.basic not found${NC}"
    exit 1
fi

if [ ! -f "install/default-config/ollama.yaml" ]; then
    echo -e "${RED}❌ install/default-config/ollama.yaml not found${NC}"
    exit 1
fi

if [ ! -f "install/default-config/inference.yaml" ]; then
    echo -e "${RED}❌ install/default-config/inference.yaml not found${NC}"
    exit 1
fi

if [ ! -f "install/orbit.db.default" ]; then
    echo -e "${RED}❌ install/orbit.db.default not found${NC}"
    exit 1
fi

# Build the image
if [ "$BUILD" = true ]; then
    echo -e "${BLUE}🔨 Building ORBIT basic Docker image...${NC}"
    
    # Ollama model configuration
    CHAT_MODEL="granite4:1b"
    EMBED_MODEL="nomic-embed-text:latest"
    OLLAMA_PORT="11434"
    
    echo -e "${GREEN}✅ Ollama configuration:${NC}"
    echo -e "${BLUE}   Chat Model: $CHAT_MODEL${NC}"
    echo -e "${BLUE}   Embeddings Model: $EMBED_MODEL${NC}"
    echo -e "${BLUE}   Port: $OLLAMA_PORT${NC}"
    echo -e "${BLUE}   Config: install/default-config/ollama.yaml${NC}"
    
    # Verify default database exists
    if [ -f "install/orbit.db.default" ]; then
        db_size=$(du -h "install/orbit.db.default" | cut -f1)
        echo -e "${GREEN}✅ Default database found: install/orbit.db.default (${db_size})${NC}"
    fi
    
    # Build the Docker image
    echo -e "${YELLOW}📦 Building Docker image (this may take a while, Ollama will pull the model during build)...${NC}"
    
    if docker build \
        -f docker/Dockerfile.basic \
        -t "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG_LATEST}" \
        .; then
        echo -e "${GREEN}✅ Docker image built successfully${NC}"
        
        # Show image info
        echo -e "${BLUE}📊 Image information:${NC}"
        docker images "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    else
        echo -e "${RED}❌ Failed to build Docker image${NC}"
        exit 1
    fi
    
    # Add version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}🏷️  Tagging image with version: $VERSION_TAG${NC}"
        docker tag "${IMAGE_NAME}:${IMAGE_TAG_BASIC}" "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
        echo -e "${GREEN}✅ Tagged as ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
    fi
fi

# Publish the image
if [ "$PUBLISH" = true ]; then
    echo -e "${BLUE}🚀 Publishing Docker image to Docker Hub...${NC}"
    
    # Push basic tag
    echo -e "${YELLOW}📤 Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}...${NC}"
    if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}"; then
        echo -e "${GREEN}✅ Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
    else
        echo -e "${RED}❌ Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}${NC}"
        exit 1
    fi
    
    # Push latest tag
    echo -e "${YELLOW}📤 Pushing ${IMAGE_NAME}:${IMAGE_TAG_LATEST}...${NC}"
    if docker push "${IMAGE_NAME}:${IMAGE_TAG_LATEST}"; then
        echo -e "${GREEN}✅ Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
    else
        echo -e "${RED}❌ Failed to push ${IMAGE_NAME}:${IMAGE_TAG_LATEST}${NC}"
        exit 1
    fi
    
    # Push version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        echo -e "${YELLOW}📤 Pushing ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}...${NC}"
        if docker push "${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"; then
            echo -e "${GREEN}✅ Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
        else
            echo -e "${RED}❌ Failed to push ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}${NC}"
            exit 1
        fi
    fi
    
    echo -e "${GREEN}🎉 Successfully published ORBIT basic image to Docker Hub!${NC}"
    echo -e "${BLUE}📋 Published tags:${NC}"
    echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
    echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_LATEST}"
    if [ -n "$VERSION_TAG" ]; then
        echo -e "   - ${IMAGE_NAME}:${IMAGE_TAG_BASIC}-${VERSION_TAG}"
    fi
    echo ""
    echo -e "${BLUE}🚀 Users can now pull and run:${NC}"
    echo -e "   docker pull ${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
    echo -e "   docker run -p 3000:3000 ${IMAGE_NAME}:${IMAGE_TAG_BASIC}"
fi

echo -e "${GREEN}✅ Done!${NC}"

