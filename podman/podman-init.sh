#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BUILD=false
REBUILD=false
VERBOSE=false
PROFILE="minimal"
DOWNLOAD_GGUF=false
PULL_MODEL=true
CREATE_DEFAULT_CONFIG=true
CONFIG_FILE=""

GGUF_MODELS_CONFIG="../install/gguf-models.json"
GGUF_MODELS_TO_DOWNLOAD=()

sed_inplace() {
    # Cross-platform sed in-place helper
    if sed --version >/dev/null 2>&1; then
        sed -i "$@"
    else
        local file="${!#}"
        local -a args=("${@:1:$#-1}")
        sed -i '' "${args[@]}" "$file"
    fi
}

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
        print(model_info['repo_id'])
        print(model_info['filename'])
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

print_help() {
    echo "Usage: ./podman-init.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build                   Build containers before starting"
    echo "  --rebuild                 Force rebuild of Podman images"
    echo "  --profile <name>          Dependency profile (minimal, torch, commercial, all)"
    echo "  --config <file>           Use specific config file"
    echo "  --no-default-config       Skip copying default config directory"
    echo "  --download-gguf [model]   Download GGUF model(s)"
    echo "  --gguf-models-config <f>  Path to gguf-models.json"
    echo "  --no-pull-model           Skip Ollama model pull"
    echo "  --verbose                 Show verbose output"
    echo "  --help                    Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./podman-init.sh --build --profile minimal"
    echo "  ./podman-init.sh --download-gguf gemma3-1b.gguf"
    echo "  ./podman-init.sh --config ../config/config.yaml"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --rebuild) REBUILD=true; BUILD=true; shift ;;
        --profile) PROFILE="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        --no-default-config) CREATE_DEFAULT_CONFIG=false; shift ;;
        --download-gguf)
            DOWNLOAD_GGUF=true
            if [[ -n "$2" && "${2:0:1}" != "-" ]]; then
                GGUF_MODELS_TO_DOWNLOAD+=("$2")
                shift 2
            else
                shift
            fi
            ;;
        --gguf-models-config) GGUF_MODELS_CONFIG="$2"; shift 2 ;;
        --no-pull-model) PULL_MODEL=false; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

echo -e "${BLUE}🚀 Initializing ORBIT Podman environment...${NC}"

if ! command -v podman &> /dev/null; then
    echo -e "${RED}❌ Podman is not installed. Please install Podman first.${NC}"
    exit 1
fi

if podman compose --help >/dev/null 2>&1; then
    PODMAN_COMPOSE="podman compose"
elif command -v podman-compose &> /dev/null; then
    PODMAN_COMPOSE="podman-compose"
else
    echo -e "${RED}❌ Podman Compose is not available. Install podman-compose or upgrade Podman.${NC}"
    exit 1
fi

if [ ! -f "compose.yml" ]; then
    echo -e "${RED}❌ compose.yml not found in current directory${NC}"
    echo -e "${YELLOW}ℹ️  Make sure you're running this script from the podman/ directory${NC}"
    exit 1
fi

echo -e "${YELLOW}📁 Creating required directories...${NC}"
mkdir -p ../logs ../data ../models ../install

if [ -n "$CONFIG_FILE" ]; then
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Specified config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi
    cp "$CONFIG_FILE" config.yaml
    echo -e "${GREEN}✅ Using config file: $CONFIG_FILE${NC}"
else
    if [ ! -d "config" ]; then
        if [ "$CREATE_DEFAULT_CONFIG" = true ]; then
            if [ -d "../config" ]; then
                echo -e "${YELLOW}⚠️  config directory not found. Copying from ../config...${NC}"
                cp -r ../config .
                echo -e "${GREEN}✅ Created config directory from ../config${NC}"
            else
                echo -e "${RED}❌ No config directory found${NC}"
                exit 1
            fi
        else
            echo -e "${RED}❌ config directory not found and --no-default-config was specified${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✅ Found existing config directory${NC}"
    fi
fi

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating...${NC}"
    if [ -f "../.env.example" ]; then
        cp ../.env.example .env
        sed_inplace 's/INTERNAL_SERVICES_MONGODB_HOST=.*/INTERNAL_SERVICES_MONGODB_HOST=mongodb/' .env
        sed_inplace 's/INTERNAL_SERVICES_REDIS_HOST=.*/INTERNAL_SERVICES_REDIS_HOST=redis/' .env
        echo -e "${GREEN}✅ Created .env with Podman-specific networking${NC}"
    else
        echo -e "${RED}❌ .env.example not found in parent directory${NC}"
        exit 1
    fi
fi

if [ "$DOWNLOAD_GGUF" = true ]; then
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}❌ curl is required to download GGUF models.${NC}"
        exit 1
    fi
    if [ ! -f "$GGUF_MODELS_CONFIG" ]; then
        echo -e "${RED}❌ GGUF models config not found: $GGUF_MODELS_CONFIG${NC}"
        exit 1
    fi

    if [ ${#GGUF_MODELS_TO_DOWNLOAD[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No GGUF models specified with --download-gguf.${NC}"
    fi

    echo -e "${YELLOW}📥 Downloading GGUF model(s)...${NC}"
    mkdir -p ../models

    for model in "${GGUF_MODELS_TO_DOWNLOAD[@]}"; do
        model_info=$(get_model_info "$model" "$GGUF_MODELS_CONFIG")
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Unknown GGUF model: $model${NC}"
            continue
        fi

        repo_id=$(echo "$model_info" | head -n 1)
        filename=$(echo "$model_info" | tail -n 1)

        if [ ! -f "../models/$filename" ]; then
            echo -e "${BLUE}ℹ️  Downloading $model from $repo_id...${NC}"
            if python3 "../install/download_hf_gguf_model.py" \
                --repo-id "$repo_id" \
                --filename "$filename" \
                --output-dir "../models"; then
                echo -e "${GREEN}✅ Downloaded to ../models/$filename${NC}"
            else
                echo -e "${RED}❌ Failed to download $model${NC}"
                exit 1
            fi
        else
            echo -e "${BLUE}ℹ️  $model already exists at ../models/$filename${NC}"
        fi
    done
fi

export DEPENDENCY_PROFILE=$PROFILE

echo -e "${YELLOW}🛑 Stopping existing containers...${NC}"
$PODMAN_COMPOSE down || true

if [ "$REBUILD" = true ]; then
    echo -e "${YELLOW}🔨 Rebuilding Podman images...${NC}"
    $PODMAN_COMPOSE build --no-cache --build-arg DEPENDENCY_PROFILE=$PROFILE
elif [ "$BUILD" = true ]; then
    echo -e "${YELLOW}🔨 Building Podman images...${NC}"
    $PODMAN_COMPOSE build --build-arg DEPENDENCY_PROFILE=$PROFILE
fi

echo -e "${YELLOW}📦 Starting Podman containers...${NC}"
if [ "$VERBOSE" = true ]; then
    $PODMAN_COMPOSE up -d
else
    $PODMAN_COMPOSE up -d >/dev/null 2>&1
fi

echo -e "${YELLOW}🔍 Checking for .env file...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env not found in podman directory${NC}"
    exit 1
else
    echo -e "${GREEN}✅ .env found${NC}"
fi

echo -e "${YELLOW}🔍 Checking config directory...${NC}"
if [ ! -d "config" ]; then
    echo -e "${RED}❌ config directory not found in podman directory${NC}"
    exit 1
else
    echo -e "${GREEN}✅ config directory present${NC}"
    ls -la config/
fi

echo -e "${YELLOW}⏳ Waiting for services...${NC}"
sleep 10

echo -e "${BLUE}📊 Checking service status...${NC}"
$PODMAN_COMPOSE ps

echo -e "${YELLOW}🏥 Testing health endpoint...${NC}"
sleep 5

HEALTH_CHECK_TIMEOUT=30
HEALTH_CHECK_INTERVAL=2
ELAPSED=0

while [ $ELAPSED -lt $HEALTH_CHECK_TIMEOUT ]; do
    if curl -f -s http://localhost:3000/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ ORBIT server is healthy!${NC}"
        break
    fi
    echo -e "${YELLOW}⏳ Waiting for server... (${ELAPSED}s/${HEALTH_CHECK_TIMEOUT}s)${NC}"
    sleep $HEALTH_CHECK_INTERVAL
    ELAPSED=$((ELAPSED + HEALTH_CHECK_INTERVAL))
done

if [ $ELAPSED -ge $HEALTH_CHECK_TIMEOUT ]; then
    echo -e "${YELLOW}⚠️  Health check timed out. Recent logs below.${NC}"
    $PODMAN_COMPOSE logs --tail=20 orbit-server
else
    $PODMAN_COMPOSE logs --tail=10 orbit-server
fi

echo -e "\n${GREEN}🎉 ORBIT Podman environment initialized!${NC}\n"
echo -e "${BLUE}Service URLs:${NC}\n  - ORBIT API: http://localhost:3000"

echo -e "${BLUE}Quick Commands:${NC}"
echo -e "  - View logs:     $PODMAN_COMPOSE logs -f orbit-server"
echo -e "  - Stop services: $PODMAN_COMPOSE down"
echo -e "  - Restart:       $PODMAN_COMPOSE restart"
echo -e "  - CLI access:    podman exec -it orbit-server orbit --help"
echo -e "  - API test:      curl -X POST http://localhost:3000/v1/chat \\\n                     -H 'Content-Type: application/json' \\\n                     -d '{\"message\": \"Hello, ORBIT!\"}'"

echo "Happy orbiting with Podman! 🚀"
