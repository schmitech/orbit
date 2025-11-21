#!/bin/bash

# Build and publish ORBIT demo Docker image to Docker Hub
# Image: schmitech/orbit:demo

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="schmitech/orbit"
IMAGE_TAG="demo"
# DOCKERFILE and BUILD_CONTEXT will be set after determining script location

# Parse command line arguments
BUILD=false
PUBLISH=false
VERSION_TAG=""
NO_CACHE=false

print_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build              Build the Docker image"
    echo "  --publish            Build and push to Docker Hub"
    echo "  --tag VERSION        Tag version (e.g., v1.0.0) - creates additional tag"
    echo "  --no-cache           Build without using cache"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --build                              # Build image locally"
    echo "  $0 --publish                            # Build and push to Docker Hub"
    echo "  $0 --publish --tag v1.0.0               # Build, push, and tag as v1.0.0"
    echo "  $0 --build --no-cache                   # Build without cache"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            ;;
        --publish)
            BUILD=true
            PUBLISH=true
            shift
            ;;
        --tag)
            VERSION_TAG="$2"
            shift 2
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --help|-h)
            print_help
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If no options provided, show help
if [ "$BUILD" = false ] && [ "$PUBLISH" = false ]; then
    print_help
fi

# Get script directory and set paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set Dockerfile and build context based on script location
# If script is in docker/ directory, Dockerfile is here and context is parent
if [ "$(basename "$SCRIPT_DIR")" = "docker" ]; then
    DOCKERFILE="Dockerfile.demo"
    BUILD_CONTEXT=".."
else
    # If script is elsewhere, assume standard structure
    DOCKERFILE="docker/Dockerfile.demo"
    BUILD_CONTEXT="."
fi

# Check if Dockerfile exists
if [ ! -f "$DOCKERFILE" ]; then
    echo -e "${RED}Error: Dockerfile not found at $DOCKERFILE${NC}"
    echo -e "${YELLOW}Current directory: $(pwd)${NC}"
    echo -e "${YELLOW}Script directory: $SCRIPT_DIR${NC}"
    exit 1
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

# Build arguments
BUILD_ARGS=()
if [ "$NO_CACHE" = true ]; then
    BUILD_ARGS+=("--no-cache")
fi

# Build image
if [ "$BUILD" = true ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
    
    echo -e "${YELLOW}Dockerfile: $DOCKERFILE${NC}"
    echo -e "${YELLOW}Context: $BUILD_CONTEXT${NC}"
    echo -e "${YELLOW}Image: $FULL_IMAGE_NAME${NC}"
    echo ""
    
    if docker build "${BUILD_ARGS[@]}" \
        -f "$DOCKERFILE" \
        -t "$FULL_IMAGE_NAME" \
        "$BUILD_CONTEXT"; then
        echo ""
        echo -e "${GREEN}✓ Image built successfully: $FULL_IMAGE_NAME${NC}"
        
        # Show image size
        IMAGE_SIZE=$(docker images "$FULL_IMAGE_NAME" --format "{{.Size}}")
        echo -e "${BLUE}  Image size: $IMAGE_SIZE${NC}"
    else
        echo ""
        echo -e "${RED}✗ Build failed${NC}"
        exit 1
    fi
fi

# Publish to Docker Hub
if [ "$PUBLISH" = true ]; then
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Publishing to Docker Hub${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # Check if logged in to Docker Hub
    if ! docker info | grep -q "Username"; then
        echo -e "${YELLOW}Not logged in to Docker Hub${NC}"
        echo -e "${YELLOW}Please login using: docker login${NC}"
        read -p "Login now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker login
        else
            echo -e "${RED}Cannot publish without Docker Hub login${NC}"
            exit 1
        fi
    fi
    
    # Push main tag
    echo -e "${YELLOW}Pushing ${IMAGE_NAME}:${IMAGE_TAG}...${NC}"
    if docker push "${IMAGE_NAME}:${IMAGE_TAG}"; then
        echo -e "${GREEN}✓ Pushed ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
    else
        echo -e "${RED}✗ Failed to push ${IMAGE_NAME}:${IMAGE_TAG}${NC}"
        exit 1
    fi
    
    # Push version tag if specified
    if [ -n "$VERSION_TAG" ]; then
        VERSION_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}-${VERSION_TAG}"
        echo ""
        echo -e "${YELLOW}Tagging as ${VERSION_IMAGE}...${NC}"
        docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "$VERSION_IMAGE"
        
        echo -e "${YELLOW}Pushing ${VERSION_IMAGE}...${NC}"
        if docker push "$VERSION_IMAGE"; then
            echo -e "${GREEN}✓ Pushed ${VERSION_IMAGE}${NC}"
        else
            echo -e "${RED}✗ Failed to push ${VERSION_IMAGE}${NC}"
            exit 1
        fi
    fi
    
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ Successfully published to Docker Hub!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}Image available at:${NC}"
    echo -e "  ${IMAGE_NAME}:${IMAGE_TAG}"
    if [ -n "$VERSION_TAG" ]; then
        echo -e "  ${IMAGE_NAME}:${IMAGE_TAG}-${VERSION_TAG}"
    fi
    echo ""
    echo -e "${BLUE}Pull command:${NC}"
    echo -e "  docker pull ${IMAGE_NAME}:${IMAGE_TAG}"
fi

