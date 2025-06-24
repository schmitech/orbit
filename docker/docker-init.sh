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

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Change to the script directory to ensure docker-compose.yml is found
cd "$SCRIPT_DIR"

print_help() {
    echo "Usage: ./docker-init.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build              Build containers before starting"
    echo "  --rebuild            Force rebuild of Docker images"
    echo "  --profile <name>     Dependency profile (minimal, torch, commercial, all)"
    echo "  --download-gguf      Download GGUF model"
    echo "  --no-pull-model      Don't pull Ollama model"
    echo "  --verbose            Show verbose output"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./docker-init.sh --build --profile minimal"
    echo "  ./docker-init.sh --rebuild --profile all --download-gguf"
    exit 0
}

# Parse command line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) BUILD=true ;;
        --rebuild) REBUILD=true; BUILD=true ;;
        --profile) PROFILE="$2"; shift ;;
        --download-gguf) DOWNLOAD_GGUF=true ;;
        --no-pull-model) PULL_MODEL=false ;;
        --verbose) VERBOSE=true ;;
        --help) print_help ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1 ;;
    esac
    shift
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

# Create necessary directories (relative to script directory)
echo -e "${YELLOW}📁 Creating required directories...${NC}"
mkdir -p ../logs ../data ../config ../gguf ../install ../configs

# Handle config file
if [ -n "$CONFIG_FILE" ]; then
    # User specified a config file
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Specified config file not found: $CONFIG_FILE${NC}"
        exit 1
    fi
    # Copy to default location
    cp "$CONFIG_FILE" ../config.yaml
    echo -e "${GREEN}✅ Using config file: $CONFIG_FILE${NC}"
    
    # Export for docker-compose
    export ORBIT_CONFIG_PATH="$CONFIG_FILE"
else
    # Check for default config.yaml in parent directory
    if [ ! -f "../config.yaml" ]; then
        if [ "$CREATE_DEFAULT_CONFIG" = true ]; then
            echo -e "${YELLOW}⚠️  config.yaml not found. Creating minimal Docker configuration...${NC}"
            
            cat > ../config.yaml << 'EOF'
# ORBIT Server Configuration - Docker Edition
general:
  host: "0.0.0.0"
  port: 3000
  inference_provider: "ollama"
  datasource_provider: "chroma"
  adapter: "qa-vector-chroma"
  verbose: false
  inference_only: false
  language_detection: true
  session_id:
    header_name: "X-Session-ID"
    required: false

# API Key settings
api_keys:
  enabled: true
  header_name: "X-API-Key"
  prefix: "orbit_"

# Logging configuration
logging:
  level: "INFO"
  handlers:
    console:
      enabled: true
      format: "text"
    file:
      enabled: true
      directory: "/app/logs"
      filename: "orbit.log"
      format: "json"
      max_size_mb: 10
      backup_count: 5

# MongoDB configuration
internal_services:
  mongodb:
    host: "mongodb"
    port: 27017
    database: "orbit"
    apikey_collection: "api_keys"
    username: ""
    password: ""

# Embedding configuration
embedding:
  provider: "ollama"
  enabled: true

embeddings:
  ollama:
    base_url: "http://ollama:11434"
    model: "nomic-embed-text"
    dimensions: 768

# Inference providers
inference:
  ollama:
    base_url: "http://ollama:11434"
    model: "llama3.2"
    temperature: 0.1
    top_p: 0.8
    top_k: 20
    repeat_penalty: 1.1
    num_predict: 1024
    num_ctx: 8192
    stream: true

# Datasource configuration
datasources:
  chroma:
    use_local: false
    host: "chroma"
    port: 8000
    embedding_provider: "ollama"

# Adapter configuration
adapters:
  - name: "qa-vector-chroma"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAChromaRetriever"
    config:
      confidence_threshold: 0.3
      distance_scaling_factor: 200.0
      embedding_provider: "ollama"
      max_results: 5
      return_results: 3

# Messages
messages:
  no_results_response: "I don't have any specific information about that topic in my knowledge base."
  collection_not_found: "The requested collection was not found."
EOF
            echo -e "${GREEN}✅ Created minimal config.yaml for Docker${NC}"
        else
            echo -e "${RED}❌ config.yaml not found and --no-default-config was specified${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✅ Found existing config.yaml${NC}"
    fi
fi

# Check for .env file in parent directory
if [ ! -f "../.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating template...${NC}"
    
    cat > ../.env << 'EOF'
# ORBIT Docker Environment Variables

# Server Configuration
ORBIT_PORT=3000
DEPENDENCY_PROFILE=minimal

# API Keys (optional - only needed for commercial providers)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
COHERE_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=
MISTRAL_API_KEY=
TOGETHER_API_KEY=

# MongoDB Configuration
MONGODB_URI=mongodb://mongodb:27017/
MONGODB_DB=orbit

# Ollama Configuration
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2

# ChromaDB Configuration
CHROMA_HOST=chroma
CHROMA_PORT=8000

# Admin Token (for API key management)
API_ADMIN_TOKEN=change_me_to_secure_token
EOF
    echo -e "${GREEN}✅ Created .env template${NC}"
    echo -e "${YELLOW}⚠️  Please edit the .env file to add your API keys if using commercial providers.${NC}"
fi

# Download GGUF model if requested
if [ "$DOWNLOAD_GGUF" = true ]; then
    echo -e "${YELLOW}📥 Downloading GGUF model...${NC}"
    mkdir -p ../gguf
    if [ ! -f "../gguf/gemma-3-1b-it-Q4_0.gguf" ]; then
        curl -L "https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_0.gguf" \
             -o "../gguf/gemma-3-1b-it-Q4_0.gguf"
        echo -e "${GREEN}✅ GGUF model downloaded${NC}"
    else
        echo -e "${BLUE}ℹ️  GGUF model already exists${NC}"
    fi
fi

# Set environment variable for dependency profile
export DEPENDENCY_PROFILE=$PROFILE

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

# Wait for services to be ready
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 10

# Check service health
echo -e "${BLUE}📊 Checking service status...${NC}"
$DOCKER_COMPOSE ps

# Pull Ollama model if needed
if [ "$PULL_MODEL" = true ]; then
    # Try to extract model from config file
    if [ -f "../config.yaml" ]; then
        OLLAMA_MODEL=$(grep -A5 "inference:" ../config.yaml | grep -A5 "ollama:" | grep "model:" | head -1 | sed 's/.*model:[[:space:]]*"\?\([^"]*\)"\?.*/\1/' | tr -d ' ')
    fi
    
    # Fallback to default if not found
    if [ -z "$OLLAMA_MODEL" ]; then
        OLLAMA_MODEL="llama3.2"
    fi
    
    echo -e "${YELLOW}🧠 Checking Ollama model: $OLLAMA_MODEL${NC}"
    
    # Check if model exists
    if ! docker exec orbit-ollama ollama list | grep -q "$OLLAMA_MODEL"; then
        echo -e "${YELLOW}📥 Pulling Ollama model...${NC}"
        docker exec orbit-ollama ollama pull $OLLAMA_MODEL
        echo -e "${GREEN}✅ Model pulled successfully${NC}"
    else
        echo -e "${GREEN}✅ Model already available${NC}"
    fi
fi

# Test the health endpoint
echo -e "${YELLOW}🏥 Testing health endpoint...${NC}"
sleep 5
if curl -f http://localhost:3000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ ORBIT server is healthy!${NC}"
else
    echo -e "${YELLOW}⚠️  Server not ready yet. Check logs with: docker compose logs orbit-server${NC}"
fi

echo -e "
${GREEN}🎉 ORBIT Docker environment initialized!${NC}

${BLUE}Service URLs:${NC}
  - ORBIT API: http://localhost:3000
  - MongoDB: mongodb://localhost:27017
  - Ollama: http://localhost:11434
  - ChromaDB: http://localhost:8000

${BLUE}Quick Commands:${NC}
  - View logs:     ${DOCKER_COMPOSE} logs -f orbit-server
  - Stop services: ${DOCKER_COMPOSE} down
  - Restart:       ${DOCKER_COMPOSE} restart
  - CLI access:    docker exec -it orbit-server orbit --help
  - API test:      curl -X POST http://localhost:3000/v1/chat \\
                     -H 'Content-Type: application/json' \\
                     -d '{\"message\": \"Hello, ORBIT!\"}'

${BLUE}Management:${NC}
  - Create API key: docker exec -it orbit-server orbit key create --name myapp
  - List API keys:  docker exec -it orbit-server orbit key list
  - Server status:  docker exec -it orbit-server orbit status

Happy orbiting! 🚀
"