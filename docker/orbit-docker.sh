#!/bin/bash

# ORBIT Docker Run Helper Script
# This script helps run ORBIT in Docker with different configurations
# Includes authentication commands that delegate to the orbit CLI inside the container

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
PROFILE="minimal"
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
    echo "  --profile <name>  Dependency profile (minimal, torch, commercial, all)"
    echo "  --port <port>     Port to expose (default: 3000)"
    echo "  --env <file>      Path to .env file (default: .env)"
    echo "  --attach          Run in foreground (default: detached)"
    echo "  --name <name>     Container name (default: orbit-server)"
    echo ""
    echo "Examples:"
    echo "  # Start with custom config"
    echo "  ./orbit-docker.sh start --config configs/production.yaml"
    echo "  # Start with config directory (default)"
    echo "  ./orbit-docker.sh start"
    echo ""
    echo "  # Start with commercial profile"
    echo "  ./orbit-docker.sh start --profile commercial"
    echo ""
    echo "  # View logs"
    echo "  ./orbit-docker.sh logs --follow"
    echo ""
    echo "  # Authentication"
    echo "  ./orbit-docker.sh login --username admin"
    echo "  ./orbit-docker.sh auth-status"
    echo "  ./orbit-docker.sh me"
    echo "  ./orbit-docker.sh logout"
    echo ""
    echo "  # Run CLI command"
    echo "  ./orbit-docker.sh cli key create --name myapp"
    echo ""
    echo "  # Execute shell in container"
    echo "  ./orbit-docker.sh exec bash"
    exit 0
}

# Parse command
if [ $# -eq 0 ]; then
    print_help
fi

COMMAND=$1
shift

# Parse options
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
        --name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --help|-h)
            print_help
            ;;
        *)
            # Keep remaining args for commands
            break
            ;;
    esac
done

# Export environment variables for docker-compose
export ORBIT_PORT=$PORT
export DEPENDENCY_PROFILE=$PROFILE

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

# Check env file
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Environment file not found: $ENV_FILE${NC}"
    echo -e "${YELLOW}Create one with: cp .env.example .env${NC}"
    exit 1
fi

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
        # If no extra args, default to orbit-server logs
        if [ $# -eq 0 ]; then
            $DOCKER_COMPOSE --env-file "$ENV_FILE" logs orbit-server
        else
            $DOCKER_COMPOSE --env-file "$ENV_FILE" logs "$@"
        fi
        ;;
        
    exec)
        if [ -z "$*" ]; then
            echo -e "${RED}❌ No command specified${NC}"
            exit 1
        fi
        docker exec -it $CONTAINER_NAME "$@"
        ;;
        
    status)
        echo -e "${BLUE}📊 ORBIT Status:${NC}"
        $DOCKER_COMPOSE --env-file "$ENV_FILE" ps
        echo ""
        echo -e "${BLUE}Health Check:${NC}"
        if curl -f http://localhost:$PORT/health > /dev/null 2>&1; then
            echo -e "${GREEN}✅ ORBIT is healthy${NC}"
        else
            echo -e "${RED}❌ ORBIT is not responding${NC}"
        fi
        ;;
        
    cli)
        # Run orbit CLI command in container
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py "$@"
        ;;
        
    login)
        echo -e "${BLUE}🔐 Logging in to ORBIT...${NC}"
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py login "$@"
        ;;
        
    logout)
        echo -e "${YELLOW}🔓 Logging out from ORBIT...${NC}"
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py logout "$@"
        ;;
        
    auth-status)
        echo -e "${BLUE}🔍 Checking authentication status...${NC}"
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py auth-status "$@"
        ;;
        
    me)
        echo -e "${BLUE}👤 Getting current user info...${NC}"
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py me "$@"
        ;;
        
    register)
        echo -e "${BLUE}👥 Registering new user...${NC}"
        docker exec -it $CONTAINER_NAME python /app/bin/orbit.py register "$@"
        ;;
        
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        print_help
        ;;
esac