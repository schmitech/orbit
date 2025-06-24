#!/bin/bash

# ORBIT Docker Run Helper Script
# This script helps run ORBIT in Docker with different configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
CONFIG_FILE=""
PROFILE="minimal"
DETACHED=true
COMMAND=""
ENV_FILE=".env"
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
    echo "Options:"
    echo "  --config <file>   Path to config.yaml file"
    echo "  --profile <name>  Dependency profile (minimal, torch, commercial, all)"
    echo "  --port <port>     Port to expose (default: 3000)"
    echo "  --env <file>      Path to .env file (default: .env)"
    echo "  --attach          Run in foreground (default: detached)"
    echo "  --name <name>     Container name (default: orbit-server)"
    echo ""
    echo "Examples:"
    echo "  # Start with custom config"
    echo "  ./orbit-docker.sh start --config configs/production.yaml"
    echo ""
    echo "  # Start with commercial profile"
    echo "  ./orbit-docker.sh start --profile commercial"
    echo ""
    echo "  # View logs"
    echo "  ./orbit-docker.sh logs --follow"
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
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi
    export ORBIT_CONFIG_PATH="$CONFIG_FILE"
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
        FOLLOW=""
        if [[ "$1" == "--follow" ]] || [[ "$1" == "-f" ]]; then
            FOLLOW="-f"
        fi
        $DOCKER_COMPOSE --env-file "$ENV_FILE" logs $FOLLOW orbit-server
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
        docker exec -it $CONTAINER_NAME orbit "$@"
        ;;
        
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        print_help
        ;;
esac