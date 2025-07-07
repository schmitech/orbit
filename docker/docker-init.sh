#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
BUILD=false
REBUILD=false
VERBOSE=false
PROFILE="minimal"
DOWNLOAD_GGUF=false
PULL_MODEL=true
CREATE_DEFAULT_CONFIG=true
CONFIG_FILE=""

# GGUF model config file (.conf)
GGUF_MODELS_CONFIG="../install/gguf-models.conf"
GGUF_MODELS_TO_DOWNLOAD=()

# Function to get URL for a model from config file
get_model_url() {
    local model_name="$1"
    local config_file="$2"
    
    if [ ! -f "$config_file" ]; then
        return 1
    fi
    
    while IFS='=' read -r model url; do
        [[ "$model" =~ ^#.*$ || -z "$model" ]] && continue  # skip comments/empty
        if [ "$model" = "$model_name" ]; then
            echo "$url"
            return 0
        fi
    done < "$config_file"
    return 1
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Change to the script directory to ensure docker-compose.yml is found
cd "$SCRIPT_DIR"

print_help() {
    echo "Usage: ./docker-init.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build                   Build containers before starting"
    echo "  --rebuild                 Force rebuild of Docker images"
    echo "  --profile <name>          Dependency profile (minimal, torch, commercial, all)"
    echo "  --config <file>           Use specific config file"
    echo "  --no-default-config       Don't create default config if none exists"
    echo "  --download-gguf [model]   Download GGUF model(s) by name (can be used multiple times)"
    echo "  --gguf-models-config <f>  Path to GGUF models .conf config (default: ../gguf-models.conf)"
    echo "  --no-pull-model           Don't pull Ollama model"
    echo "  --verbose                 Show verbose output"
    echo "  --help                    Show this help message"
    echo ""
    echo "GGUF models .conf example (../install/gguf-models.conf):"
    echo "gemma-3-1b=https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_0.gguf"
    echo "my-kaggle-model.gguf=https://www.kaggle.com/models/your/model/download/my-kaggle-model.gguf"
    echo ""
    echo "Examples:"
    echo "  ./docker-init.sh --build --profile minimal"
    echo "  ./docker-init.sh --rebuild --profile all --download-gguf gemma-3-1b"
    echo "  ./docker-init.sh --download-gguf my-kaggle-model.gguf --gguf-models-config ../my-gguf-list.conf"
    echo "  ./docker-init.sh --download-gguf gemma-3-1b --download-gguf another-model.gguf"
    echo "  ./docker-init.sh --config /path/to/config.yaml"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build) BUILD=true; shift ;;
        --rebuild) REBUILD=true; BUILD=true; shift ;;
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
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
        --gguf-models-config)
            GGUF_MODELS_CONFIG="$2"
            shift 2
            ;;
        --no-pull-model) PULL_MODEL=false; shift ;;
        --verbose) VERBOSE=true; shift ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
done

echo -e "${BLUE}🚀 Initializing ORBIT Docker environment...${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if docker compose is available
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

# Ensure DOCKER_COMPOSE is set
if [ -z "$DOCKER_COMPOSE" ]; then
    echo -e "${RED}❌ Internal error: DOCKER_COMPOSE variable is not set. Exiting.${NC}"
    exit 1
fi

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ docker-compose.yml not found in current directory${NC}"
    echo -e "${YELLOW}ℹ️  Make sure you're running this script from the docker/ directory${NC}"
    exit 1
fi

# Create necessary directories (relative to script directory)
echo -e "${YELLOW}📁 Creating required directories...${NC}"
mkdir -p ../logs ../data ../gguf ../install

# Handle config file
if [ -n "$CONFIG_FILE" ]; then
    # User specified a config file
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Specified config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi
    # Copy to docker directory for consistency with .env
    cp "$CONFIG_FILE" config.yaml
    echo -e "${GREEN}✅ Using config file: $CONFIG_FILE${NC}"
else
    # Check for config.yaml in docker directory first, then parent directory
    if [ ! -f "config.yaml" ]; then
        if [ "$CREATE_DEFAULT_CONFIG" = true ]; then
            if [ -f "../config.yaml" ]; then
                echo -e "${YELLOW}⚠️  config.yaml not found. Copying from config.yaml...${NC}"
                cp ../config.yaml config.yaml
                echo -e "${GREEN}✅ Created new config.yaml from ${NC}"
                echo -e "${BLUE}ℹ️  You may want to review and customize the configuration in config.yaml${NC}"
            else
                echo -e "${RED}❌ No config.yaml found${NC}"
                echo -e "${YELLOW}ℹ️  Please ensure config.yaml exists in the parent directory${NC}"
                exit 1
            fi
        else
            echo -e "${RED}❌ config.yaml not found and --no-default-config was specified${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✅ Found existing config.yaml${NC}"
    fi
fi

# Check for .env file in parent directory
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating...${NC}"
    if [ -f "../.env.example" ]; then
        cp ../.env.example .env
        
        # Substitute Docker service hostnames for containerized environment
        echo -e "${YELLOW}🔧 Configuring .env for Docker environment...${NC}"
        sed -i 's/INTERNAL_SERVICES_MONGODB_HOST=.*/INTERNAL_SERVICES_MONGODB_HOST=mongodb/' .env
        sed -i 's/INTERNAL_SERVICES_REDIS_HOST=.*/INTERNAL_SERVICES_REDIS_HOST=redis/' .env
        
        echo -e "${GREEN}✅ Created .env with Docker-specific configuration${NC}"
        echo -e "${BLUE}ℹ️  You may want to review and customize other environment variables in .env${NC}"
    else
        echo -e "${RED}❌ .env.example not found${NC}"
        echo -e "${YELLOW}ℹ️  Please ensure .env.example exists in the parent directory${NC}"
        exit 1
    fi
fi

# Check if curl is available for GGUF download
if [ "$DOWNLOAD_GGUF" = true ]; then
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}❌ curl is not installed. Please install curl to download GGUF models.${NC}"
        exit 1
    fi
    if [ ! -f "$GGUF_MODELS_CONFIG" ]; then
        echo -e "${RED}❌ GGUF models config file not found: $GGUF_MODELS_CONFIG${NC}"
        exit 1
    fi

    if [ ${#GGUF_MODELS_TO_DOWNLOAD[@]} -eq 0 ]; then
        echo -e "${YELLOW}⚠️  No GGUF models specified. Use --download-gguf <name> to specify models to download.${NC}"
    fi

    echo -e "${YELLOW}📥 Downloading GGUF model(s)...${NC}"
    mkdir -p ../gguf

    for model in "${GGUF_MODELS_TO_DOWNLOAD[@]}"; do
        url=$(get_model_url "$model" "$GGUF_MODELS_CONFIG")
        if [ -z "$url" ]; then
            echo -e "${RED}❌ Unknown GGUF model: $model (not found in $GGUF_MODELS_CONFIG)${NC}"
            continue
        fi
        if [ ! -f "../gguf/$model" ]; then
            echo -e "${BLUE}ℹ️  Downloading $model...${NC}"
            if curl -L "$url" -o "../gguf/$model" --progress-bar; then
                echo -e "${GREEN}✅ $model downloaded successfully${NC}"
            else
                echo -e "${RED}❌ Failed to download $model${NC}"
                exit 1
            fi
        else
            echo -e "${BLUE}ℹ️  $model already exists${NC}"
        fi
    done
fi

# Set environment variable for dependency profile
export DEPENDENCY_PROFILE=$PROFILE

# Always stop and remove old containers before building or starting new ones
echo -e "${YELLOW}🛑 Stopping existing containers...${NC}"
$DOCKER_COMPOSE down

# Build or rebuild if requested
if [ "$REBUILD" = true ]; then
    echo -e "${YELLOW}🔨 Rebuilding Docker images...${NC}"
    $DOCKER_COMPOSE build --no-cache --build-arg DEPENDENCY_PROFILE=$PROFILE
elif [ "$BUILD" = true ]; then
    echo -e "${YELLOW}🔨 Building Docker images...${NC}"
    $DOCKER_COMPOSE build --build-arg DEPENDENCY_PROFILE=$PROFILE
fi

# Start the services
echo -e "${YELLOW}🐳 Starting Docker containers...${NC}"
if [ "$VERBOSE" = true ]; then
    $DOCKER_COMPOSE up -d
else
    $DOCKER_COMPOSE up -d > /dev/null 2>&1
fi

# Sanity check: ensure .env exists locally and will be mounted
echo -e "${YELLOW}🔍 Checking for .env in docker directory...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env not found in docker directory!${NC}"
    echo -e "${YELLOW}This file should have been created earlier in the initialization process.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ .env found in docker directory.${NC}"
fi

# Sanity check: ensure config.yaml exists locally and will be mounted
echo -e "${YELLOW}🔍 Checking for config.yaml in docker directory...${NC}"
if [ ! -f "config.yaml" ]; then
    echo -e "${RED}❌ config.yaml not found in docker directory!${NC}"
    echo -e "${YELLOW}This file should have been created earlier in the initialization process.${NC}"
    exit 1
else
    echo -e "${GREEN}✅ config.yaml found in docker directory.${NC}"
fi

# Wait for services to be ready
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 10

# Check service health
echo -e "${BLUE}📊 Checking service status...${NC}"
$DOCKER_COMPOSE ps

# Test the health endpoint with timeout
echo -e "${YELLOW}🏥 Testing health endpoint...${NC}"
sleep 5

# Try health check with timeout
HEALTH_CHECK_TIMEOUT=30
HEALTH_CHECK_INTERVAL=2
ELAPSED=0

while [ $ELAPSED -lt $HEALTH_CHECK_TIMEOUT ]; do
    if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ ORBIT server is healthy!${NC}"
        break
    fi
    
    echo -e "${YELLOW}⏳ Waiting for server to be ready... (${ELAPSED}s/${HEALTH_CHECK_TIMEOUT}s)${NC}"
    sleep $HEALTH_CHECK_INTERVAL
    ELAPSED=$((ELAPSED + HEALTH_CHECK_INTERVAL))
done

if [ $ELAPSED -ge $HEALTH_CHECK_TIMEOUT ]; then
    echo -e "${YELLOW}⚠️  Server health check timed out. Showing recent logs...${NC}"
    echo -e "${BLUE}📋 Last 20 lines of orbit-server logs:${NC}"
    $DOCKER_COMPOSE logs --tail=20 orbit-server
    echo -e "${YELLOW}ℹ️  For full logs, run: $DOCKER_COMPOSE logs orbit-server${NC}"
else
    echo -e "${BLUE}📋 Showing recent logs to verify startup:${NC}"
    $DOCKER_COMPOSE logs --tail=10 orbit-server
fi

echo -e "
${GREEN}🎉 ORBIT Docker environment initialized!${NC}

${BLUE}Service URLs:${NC}
  - ORBIT API: http://localhost:3000
  
${BLUE}Quick Commands:${NC}
  - View logs:     $DOCKER_COMPOSE logs -f orbit-server
  - Stop services: $DOCKER_COMPOSE down
  - Restart:       $DOCKER_COMPOSE restart
  - CLI access:    docker exec -it orbit-server orbit --help
  - API test:      curl -X POST http://localhost:3000/v1/chat \\
                     -H 'Content-Type: application/json' \\
                     -d '{\"message\": \"Hello, ORBIT!\"}'

Happy orbiting! 🚀
"