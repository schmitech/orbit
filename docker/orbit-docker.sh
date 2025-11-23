#!/bin/bash

# ORBIT Docker Run Helper Script
# ===============================
# This script helps run ORBIT in Docker with different configurations.
# It acts as a proxy to the orbit CLI inside any Docker container.
#
# QUICK START EXAMPLES:
# --------------------
#
# Basic Usage (default container 'orbit-server'):
#   ./orbit-docker.sh status                    # Check container status
#   ./orbit-docker.sh logs --follow             # View logs
#   ./orbit-docker.sh cli key list              # List API keys
#   ./orbit-docker.sh login --username admin    # Login to ORBIT
#
# Using Specific Container (--container option):
#   ./orbit-docker.sh --container demo status        # Check 'demo' container status
#   ./orbit-docker.sh --container demo logs          # View logs from 'demo' container
#   ./orbit-docker.sh --container demo cli key list  # List keys in 'demo' container
#   ./orbit-docker.sh --container demo login --username admin  # Login to 'demo' container
#
# Container Management:
#   ./orbit-docker.sh start                     # Start ORBIT (docker-compose)
#   ./orbit-docker.sh stop                      # Stop ORBIT (docker-compose)
#   ./orbit-docker.sh restart                   # Restart ORBIT (docker-compose)
#   ./orbit-docker.sh exec bash                  # Open shell in container
#   ./orbit-docker.sh --container demo exec bash     # Open shell in 'demo' container
#
# CLI Commands (proxy to orbit CLI):
#   ./orbit-docker.sh cli key create --name myapp
#   ./orbit-docker.sh cli key list
#   ./orbit-docker.sh cli key delete --key orbit_xxxxx
#   ./orbit-docker.sh cli prompt list
#   ./orbit-docker.sh cli user list
#
# Authentication Commands:
#   ./orbit-docker.sh login --username admin
#   ./orbit-docker.sh logout
#   ./orbit-docker.sh auth-status
#   ./orbit-docker.sh me
#   ./orbit-docker.sh register --username newuser --role user
#
# Advanced Usage:
#   ./orbit-docker.sh start --config configs/prod.yaml --profile cloud
#   ./orbit-docker.sh start --port 8080
#   ./orbit-docker.sh logs --tail 100 --follow
#   ./orbit-docker.sh --container orbit-basic status
#
# For more details, run: ./orbit-docker.sh --help

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Remember the original working directory for relative paths
ORIGINAL_DIR="$(pwd)"
# Change to the script directory to ensure docker-compose.yml is found
cd "$SCRIPT_DIR"

# Default values
CONFIG_FILE=""
PROFILE=""
DETACHED=true
COMMAND=""
ENV_FILE="../.env"
PORT="3000"
CONTAINER_NAME="orbit-server"

# Docker compose detection
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}❌ Docker Compose is not installed.${NC}"
    exit 1
fi

print_help() {
    echo "ORBIT Docker Run Helper"
    echo ""
    echo "Usage: ./orbit-docker.sh [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start             Start ORBIT with specified config"
    echo "  stop              Stop ORBIT containers"
    echo "  restart           Restart ORBIT containers"
    echo "  logs              Show ORBIT logs"
    echo "  exec              Execute command in ORBIT container"
    echo "  status            Show container status"
    echo "  cli               Run ORBIT CLI command"
    echo ""
    echo "Authentication Commands:"
    echo "  login             Login to ORBIT server"
    echo "  logout            Logout from ORBIT server"
    echo "  auth-status       Check authentication status"
    echo "  me                Show current user information"
    echo "  register          Register a new user (admin only)"
    echo ""
    echo "Note: Authentication commands require the ORBIT server to be running."
    echo ""
    echo "Options:"
    echo "  --config <file>   Path to config file (overrides config directory)"
    echo "  --profile <name>  Dependency profile (torch, cloud, all) - omit for default dependencies only"
    echo "  --port <port>     Port to expose (default: 3000)"
    echo "  --env <file>      Path to .env file (default: .env)"
    echo "  --attach          Run in foreground (default: detached)"
    echo "  --container <name> Container name to target (default: orbit-server)"
    echo "                    Use this to work with any ORBIT container, not just docker-compose ones"
    echo ""
    echo "Examples:"
    echo ""
    echo "Container Management (docker-compose):"
    echo "  ./orbit-docker.sh start                    # Start ORBIT"
    echo "  ./orbit-docker.sh start --profile cloud    # Start with cloud profile"
    echo "  ./orbit-docker.sh stop                     # Stop ORBIT"
    echo "  ./orbit-docker.sh restart                  # Restart ORBIT"
    echo ""
    echo "Working with Any Container (--container option):"
    echo "  ./orbit-docker.sh --container demo status       # Check 'demo' container status"
    echo "  ./orbit-docker.sh --container demo logs         # View logs from 'demo' container"
    echo "  ./orbit-docker.sh --container demo logs --follow # Follow logs from 'demo' container"
    echo "  ./orbit-docker.sh --container orbit-basic exec bash  # Open shell in 'orbit-basic' container"
    echo ""
    echo "CLI Commands (proxy to orbit CLI):"
    echo "  ./orbit-docker.sh cli key list            # List API keys (default container)"
    echo "  ./orbit-docker.sh --container demo cli key list # List keys in 'demo' container"
    echo "  ./orbit-docker.sh cli key create --name myapp"
    echo "  ./orbit-docker.sh cli prompt list"
    echo "  ./orbit-docker.sh cli user list"
    echo ""
    echo "Authentication:"
    echo "  ./orbit-docker.sh login --username admin   # Login (default container)"
    echo "  ./orbit-docker.sh --container demo login --username admin  # Login to 'demo' container"
    echo "  ./orbit-docker.sh auth-status             # Check auth status"
    echo "  ./orbit-docker.sh me                       # Show current user"
    echo "  ./orbit-docker.sh logout                   # Logout"
    echo ""
    echo "Advanced:"
    echo "  ./orbit-docker.sh start --config configs/prod.yaml"
    echo "  ./orbit-docker.sh start --port 8080"
    echo "  ./orbit-docker.sh logs --tail 100 --follow"
    exit 0
}

# Parse command and options (options can come before or after command)
if [ $# -eq 0 ]; then
    print_help
fi

COMMAND=""
REMAINING_ARGS=()

# First pass: parse options and find the command
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --env)
            ENV_FILE="$2"
            shift 2
            ;;
        --attach)
            DETACHED=false
            shift
            ;;
        --container)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --name)
            # Deprecated: use --container instead
            echo -e "${YELLOW}⚠️  --name is deprecated, use --container instead${NC}" >&2
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --help|-h)
            print_help
            ;;
        *)
            # First non-option argument is the command
            if [ -z "$COMMAND" ]; then
                COMMAND="$1"
            else
                # Remaining args for the command
                REMAINING_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

# If no command found, show help
if [ -z "$COMMAND" ]; then
    echo -e "${RED}❌ No command specified${NC}"
    print_help
fi

# Set remaining args for commands that need them
set -- "${REMAINING_ARGS[@]}"

# Export environment variables for docker-compose
export ORBIT_PORT=$PORT
export DEPENDENCY_PROFILE=${PROFILE:-}

# Handle config file
if [ -n "$CONFIG_FILE" ]; then
    # If CONFIG_FILE is a relative path, make it relative to the original directory
    if [[ "$CONFIG_FILE" != /* ]]; then
        CONFIG_FILE="$ORIGINAL_DIR/$CONFIG_FILE"
    fi
    
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi
    export CONFIG_PATH="$CONFIG_FILE"
    echo -e "${BLUE}Using config: $CONFIG_FILE${NC}"
fi

# Check env file (only for docker-compose commands that actually need it)
# Skip check if using --container with status/logs (using direct docker commands)
NEEDS_ENV_FILE=false
if [[ "$COMMAND" =~ ^(start|stop|restart)$ ]]; then
    NEEDS_ENV_FILE=true
elif [[ "$COMMAND" =~ ^(status|logs)$ ]] && [ "$CONTAINER_NAME" = "orbit-server" ]; then
    # Only need env file for docker-compose commands (default container)
    NEEDS_ENV_FILE=true
fi

if [ "$NEEDS_ENV_FILE" = true ]; then
    # Resolve env file path relative to script directory
    if [[ "$ENV_FILE" != /* ]]; then
        ENV_FILE="$SCRIPT_DIR/$ENV_FILE"
    fi
    
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}❌ Environment file not found: $ENV_FILE${NC}"
        echo -e "${YELLOW}Note: The .env file is only needed for docker-compose commands (start, stop, restart)${NC}"
        echo -e "${YELLOW}When using --container with status/logs, the .env file is not required${NC}"
        echo ""
        echo -e "${YELLOW}To create the .env file:${NC}"
        echo -e "  cp ../env.example $ENV_FILE"
        echo -e "  # Or from docker directory: cp env.example .env"
        exit 1
    fi
fi

# Function to check if container exists
check_container_exists() {
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${RED}❌ Container '$CONTAINER_NAME' not found${NC}"
        echo -e "${YELLOW}Available containers:${NC}"
        docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | head -10
        exit 1
    fi
}

# Execute commands
case $COMMAND in
    start)
        echo -e "${BLUE}🚀 Starting ORBIT...${NC}"
        echo -e "${BLUE}Profile: $PROFILE${NC}"
        
        if [ "$DETACHED" = true ]; then
            $DOCKER_COMPOSE --env-file "$ENV_FILE" up -d
            echo -e "${GREEN}✅ ORBIT started in background${NC}"
            echo -e "${YELLOW}View logs with: ./orbit-docker.sh logs${NC}"
        else
            $DOCKER_COMPOSE --env-file "$ENV_FILE" up
        fi
        ;;
        
    stop)
        echo -e "${YELLOW}🛑 Stopping ORBIT...${NC}"
        $DOCKER_COMPOSE --env-file "$ENV_FILE" down
        echo -e "${GREEN}✅ ORBIT stopped${NC}"
        ;;
        
    restart)
        echo -e "${YELLOW}🔄 Restarting ORBIT...${NC}"
        $DOCKER_COMPOSE --env-file "$ENV_FILE" restart
        echo -e "${GREEN}✅ ORBIT restarted${NC}"
        ;;
        
    logs)
        # If --container is specified, use docker logs directly
        if [ "$CONTAINER_NAME" != "orbit-server" ]; then
            check_container_exists
            docker logs "$CONTAINER_NAME" "$@"
        else
            # Use docker-compose for default container
            if [ $# -eq 0 ]; then
                $DOCKER_COMPOSE --env-file "$ENV_FILE" logs orbit-server
            else
                $DOCKER_COMPOSE --env-file "$ENV_FILE" logs "$@"
            fi
        fi
        ;;
        
    exec)
        if [ -z "$*" ]; then
            echo -e "${RED}❌ No command specified${NC}"
            exit 1
        fi
        check_container_exists
        docker exec -it $CONTAINER_NAME "$@"
        ;;
        
    status)
        # If --container is specified, check that specific container
        if [ "$CONTAINER_NAME" != "orbit-server" ]; then
            check_container_exists
            echo -e "${BLUE}📊 Container Status:${NC}"
            docker ps --filter "name=^${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
            echo ""
            echo -e "${BLUE}Health Check:${NC}"
            # Try to get port from container (compatible with both GNU and BSD grep)
            CONTAINER_PORT=$(docker port "$CONTAINER_NAME" 2>/dev/null | grep '3000/tcp' | sed -E 's/.*:([0-9]+).*/\1/' | head -1 || echo "$PORT")
            if curl -f http://localhost:${CONTAINER_PORT:-$PORT}/health > /dev/null 2>&1; then
                echo -e "${GREEN}✅ Container '$CONTAINER_NAME' is healthy${NC}"
            else
                echo -e "${YELLOW}⚠️  Container '$CONTAINER_NAME' is running but health check failed${NC}"
                echo -e "${YELLOW}   (This is normal if the container just started)${NC}"
            fi
        else
            # Use docker-compose for default
            echo -e "${BLUE}📊 ORBIT Status:${NC}"
            $DOCKER_COMPOSE --env-file "$ENV_FILE" ps
            echo ""
            echo -e "${BLUE}Health Check:${NC}"
            if curl -f http://localhost:$PORT/health > /dev/null 2>&1; then
                echo -e "${GREEN}✅ ORBIT is healthy${NC}"
            else
                echo -e "${RED}❌ ORBIT is not responding${NC}"
            fi
        fi
        ;;
        
    cli)
        # Run orbit CLI command in container
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py "$@"
        ;;
        
    login)
        echo -e "${BLUE}🔐 Logging in to ORBIT...${NC}"
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py login "$@"
        ;;
        
    logout)
        echo -e "${YELLOW}🔓 Logging out from ORBIT...${NC}"
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py logout "$@"
        ;;
        
    auth-status)
        echo -e "${BLUE}🔍 Checking authentication status...${NC}"
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py auth-status "$@"
        ;;
        
    me)
        echo -e "${BLUE}👤 Getting current user info...${NC}"
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py me "$@"
        ;;
        
    register)
        echo -e "${BLUE}👥 Registering new user...${NC}"
        check_container_exists
        docker exec -it $CONTAINER_NAME python /orbit/bin/orbit.py register "$@"
        ;;
        
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        print_help
        ;;
esac