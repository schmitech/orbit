#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
CLEAN_DEMO_ONLY=false
CLEAN_ALL=false
CLEAN_UNUSED=false
FORCE=false
NO_CONFIRM=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --demo-only)
            CLEAN_DEMO_ONLY=true
            shift
            ;;
        --all)
            CLEAN_ALL=true
            shift
            ;;
        --unused)
            CLEAN_UNUSED=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --yes|-y)
            NO_CONFIRM=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --demo-only    Clean up only orbit-demo container and image"
            echo "  --unused       Remove unused containers, images, volumes, and networks"
            echo "  --all          Remove ALL containers, images, volumes, and networks (DANGEROUS)"
            echo "  --force        Force removal without confirmation (use with caution)"
            echo "  --yes, -y      Skip confirmation prompts"
            echo "  --help, -h     Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --demo-only              # Clean up only orbit-demo"
            echo "  $0 --unused                 # Remove unused Docker resources"
            echo "  $0 --all --yes              # Remove everything (no confirmation)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If no options specified, default to demo-only
if [ "$CLEAN_DEMO_ONLY" = false ] && [ "$CLEAN_ALL" = false ] && [ "$CLEAN_UNUSED" = false ]; then
    CLEAN_DEMO_ONLY=true
fi

echo -e "${BLUE}=== Docker Cleanup Script ===${NC}"

# Function to confirm action
confirm() {
    if [ "$NO_CONFIRM" = true ] || [ "$FORCE" = true ]; then
        return 0
    fi
    read -p "$1 (y/N): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# Clean up orbit-demo only
clean_demo() {
    echo -e "${YELLOW}Cleaning up orbit-demo container and image...${NC}"
    
    # Stop and remove container
    if docker ps -a --format '{{.Names}}' | grep -q "^orbit-demo$"; then
        echo "Stopping orbit-demo container..."
        docker stop orbit-demo 2>/dev/null || true
        echo "Removing orbit-demo container..."
        docker rm orbit-demo 2>/dev/null || true
        echo -e "${GREEN}✓ orbit-demo container removed${NC}"
    else
        echo -e "${YELLOW}orbit-demo container not found${NC}"
    fi
    
    # Remove image
    if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^schmitech/orbit:demo$"; then
        echo "Removing schmitech/orbit:demo image..."
        docker rmi schmitech/orbit:demo 2>/dev/null || true
        echo -e "${GREEN}✓ orbit-demo image removed${NC}"
    else
        echo -e "${YELLOW}schmitech/orbit:demo image not found${NC}"
    fi
}

# Clean unused resources
clean_unused() {
    echo -e "${YELLOW}Removing unused Docker resources...${NC}"
    
    echo "Removing unused containers..."
    docker container prune -f
    
    echo "Removing unused images..."
    docker image prune -f
    
    echo "Removing unused volumes..."
    docker volume prune -f
    
    echo "Removing unused networks..."
    docker network prune -f
    
    echo "Cleaning up Docker builder cache..."
    docker builder prune -f
    
    echo -e "${GREEN}✓ Unused resources cleaned${NC}"
}

# Clean everything (DANGEROUS)
clean_all() {
    if ! confirm "${RED}WARNING: This will remove ALL containers, images, volumes, and networks. Continue?${NC}"; then
        echo -e "${YELLOW}Aborted${NC}"
        exit 0
    fi
    
    echo -e "${RED}Stopping all running containers...${NC}"
    docker stop $(docker ps -q) 2>/dev/null || true
    
    echo -e "${RED}Removing all containers...${NC}"
    docker rm $(docker ps -a -q) 2>/dev/null || true
    
    echo -e "${RED}Removing all images...${NC}"
    docker rmi -f $(docker images -q) 2>/dev/null || true
    
    echo -e "${RED}Removing all volumes...${NC}"
    docker volume rm $(docker volume ls -q) 2>/dev/null || true
    
    echo -e "${RED}Removing unused networks...${NC}"
    docker network prune -f
    
    echo -e "${RED}Performing system prune...${NC}"
    docker system prune -a -f --volumes
    
    echo -e "${RED}Cleaning up Docker builder cache...${NC}"
    docker builder prune -a -f
    
    echo -e "${GREEN}✓ All Docker resources removed${NC}"
} 

# Execute cleanup based on options
if [ "$CLEAN_DEMO_ONLY" = true ]; then
    clean_demo
fi

if [ "$CLEAN_UNUSED" = true ]; then
    if confirm "Remove unused containers, images, volumes, and networks?"; then
        clean_unused
    else
        echo -e "${YELLOW}Skipping unused resources cleanup${NC}"
    fi
fi

if [ "$CLEAN_ALL" = true ]; then
    clean_all
fi

# Check for open ports (useful for orbit-demo)
echo ""
echo -e "${BLUE}Checking for open Docker-related ports (3000, 5432, 6379, 8000, 8080, 9000)...${NC}"
PORTS=(3000 5432 6379 8000 8080 9000)
ANY_OPEN=false
for PORT in "${PORTS[@]}"; do
    if lsof -i :$PORT &>/dev/null 2>&1 || netstat -an | grep -q ":$PORT " 2>/dev/null; then
        echo -e "${YELLOW}Port $PORT is still in use${NC}"
        ANY_OPEN=true
    fi
done
if [ "$ANY_OPEN" = false ]; then
    echo -e "${GREEN}All checked ports are free${NC}"
fi

# Show Docker state
echo ""
echo -e "${BLUE}==== Docker State After Cleanup ====${NC}"
echo ""
echo -e "${BLUE}Containers:${NC}"
docker ps -a 2>/dev/null || echo "No containers"

echo ""
echo -e "${BLUE}Images:${NC}"
docker images 2>/dev/null || echo "No images"

echo ""
echo -e "${BLUE}Volumes:${NC}"
docker volume ls 2>/dev/null || echo "No volumes"

echo ""
echo -e "${BLUE}Networks:${NC}"
docker network ls 2>/dev/null || echo "No networks"

echo ""
echo -e "${BLUE}Docker system info:${NC}"
docker system df 2>/dev/null || echo "Unable to get system info"

echo ""
echo -e "${GREEN}=== Cleanup Complete ===${NC}" 