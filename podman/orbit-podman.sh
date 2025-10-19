#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_DIR="$(pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE=""
PROFILE="minimal"
DETACHED=true
COMMAND=""
ENV_FILE="../.env"
PORT="3000"
CONTAINER_NAME="orbit-server"

if command -v podman >/dev/null 2>&1; then
    if podman compose --help >/dev/null 2>&1; then
        PODMAN_COMPOSE="podman compose"
    elif command -v podman-compose >/dev/null 2>&1; then
        PODMAN_COMPOSE="podman-compose"
    else
        echo -e "${RED}❌ Podman Compose is not installed.${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Podman is not installed.${NC}"
    exit 1
fi

print_help() {
    echo "ORBIT Podman Helper"
    echo ""
    echo "Usage: ./orbit-podman.sh [COMMAND] [OPTIONS]"
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
    echo "Auth shortcuts:" 
    echo "  login | logout | auth-status | me | register"
    echo ""
    echo "Options:"
    echo "  --config <file>   Path to config file"
    echo "  --profile <name>  Dependency profile"
    echo "  --port <port>     Port to expose (default: 3000)"
    echo "  --env <file>      Path to .env file (default: ../.env)"
    echo "  --attach          Run in foreground"
    echo "  --name <name>     Container name (default: orbit-server)"
    echo ""
    echo "Examples:"
    echo "  ./orbit-podman.sh start --profile cloud"
    echo "  ./orbit-podman.sh logs --follow"
    echo "  ./orbit-podman.sh cli key list"
    exit 0
}

if [ $# -eq 0 ]; then
    print_help
fi

COMMAND=$1
shift

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"; shift 2 ;;
        --profile)
            PROFILE="$2"; shift 2 ;;
        --port)
            PORT="$2"; shift 2 ;;
        --env)
            ENV_FILE="$2"; shift 2 ;;
        --attach)
            DETACHED=false; shift ;;
        --name)
            CONTAINER_NAME="$2"; shift 2 ;;
        --help|-h)
            print_help ;;
        *)
            break ;;
    esac
done

export ORBIT_PORT=$PORT
export DEPENDENCY_PROFILE=$PROFILE

if [ -n "$CONFIG_FILE" ]; then
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

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Environment file not found: $ENV_FILE${NC}"
    echo -e "${YELLOW}Create one with: cp env.example .env${NC}"
    exit 1
fi

case $COMMAND in
    start)
        echo -e "${BLUE}🚀 Starting ORBIT with Podman...${NC}"
        echo -e "${BLUE}Profile: $PROFILE${NC}"
        if [ "$DETACHED" = true ]; then
            $PODMAN_COMPOSE --env-file "$ENV_FILE" up -d
            echo -e "${GREEN}✅ ORBIT started in background${NC}"
        else
            $PODMAN_COMPOSE --env-file "$ENV_FILE" up
        fi
        ;;
    stop)
        echo -e "${YELLOW}🛑 Stopping ORBIT...${NC}"
        $PODMAN_COMPOSE --env-file "$ENV_FILE" down
        echo -e "${GREEN}✅ ORBIT stopped${NC}"
        ;;
    restart)
        echo -e "${YELLOW}🔄 Restarting ORBIT...${NC}"
        $PODMAN_COMPOSE --env-file "$ENV_FILE" restart
        echo -e "${GREEN}✅ ORBIT restarted${NC}"
        ;;
    logs)
        if [ $# -eq 0 ]; then
            $PODMAN_COMPOSE --env-file "$ENV_FILE" logs orbit-server
        else
            $PODMAN_COMPOSE --env-file "$ENV_FILE" logs "$@"
        fi
        ;;
    exec)
        if [ -z "$*" ]; then
            echo -e "${RED}❌ No command specified${NC}"
            exit 1
        fi
        podman exec -it $CONTAINER_NAME "$@"
        ;;
    status)
        echo -e "${BLUE}📊 ORBIT Status:${NC}"
        $PODMAN_COMPOSE --env-file "$ENV_FILE" ps
        echo ""
        echo -e "${BLUE}Health Check:${NC}"
        if curl -f http://localhost:$PORT/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ ORBIT is healthy${NC}"
        else
            echo -e "${RED}❌ ORBIT is not responding${NC}"
        fi
        ;;
    cli)
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py "$@"
        ;;
    login)
        echo -e "${BLUE}🔐 Logging in to ORBIT...${NC}"
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py login "$@"
        ;;
    logout)
        echo -e "${YELLOW}🔓 Logging out from ORBIT...${NC}"
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py logout "$@"
        ;;
    auth-status)
        echo -e "${BLUE}🔍 Checking authentication status...${NC}"
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py auth-status "$@"
        ;;
    me)
        echo -e "${BLUE}👤 Getting current user info...${NC}"
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py me "$@"
        ;;
    register)
        echo -e "${BLUE}👥 Registering new user...${NC}"
        podman exec -it $CONTAINER_NAME python /app/bin/orbit.py register "$@"
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        print_help
        ;;
esac
