#!/bin/bash

set -e

# Parse command line arguments
BUILD=false
REBUILD_IMAGE=false
VERBOSE=false

print_help() {
    echo "Usage: ./docker-init.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build          Build containers before starting"
    echo "  --rebuild-image  Rebuild the ORBIT Docker image from scratch"
    echo "  --verbose        Show verbose output"
    echo "  --help           Show this help message"
    echo ""
    exit 0
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) BUILD=true ;;
        --rebuild-image) REBUILD_IMAGE=true; BUILD=true ;;
        --verbose) VERBOSE=true ;;
        --help) print_help ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "🚀 Initializing ORBIT Docker environment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating required directories..."
mkdir -p logs data config

# Check for required files
if [ ! -f "config/config.yaml" ]; then
    echo "⚠️ config.yaml not found. Creating example configuration..."
    
    # Create example config if it doesn't exist
    cat > config/config.yaml << 'EOF'
# ORBIT Server Configuration - Docker Edition
general:
  host: "0.0.0.0"
  port: 3000
  inference_provider: "ollama"
  datasource_provider: "chroma"
  adapter: "qa"
  verbose: false
  inference_only: false
  language_detection: true

# API Key settings
api_keys:
  enabled: true
  header_name: "X-API-Key"
  require_for_health: false

# Logging configuration
logging:
  level: "INFO"
  console:
    enabled: true
    format: "text"
  file:
    enabled: true
    format: "json"
    directory: "/app/logs"
    filename: "orbit.log"

# MongoDB configuration for API key storage
mongodb:
  connection_string: "${MONGODB_URI:-mongodb://mongodb:27017/}"
  database_name: "${MONGODB_DB:-orbit}"

# Provider configuration
inference:
  ollama:
    base_url: "${OLLAMA_BASE_URL:-http://ollama:11434}"
    model: "${OLLAMA_MODEL:-llama3}"
  openai:
    api_key: "${OPENAI_API_KEY}"
    model: "${OPENAI_MODEL:-gpt-4}"
  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
    model: "${ANTHROPIC_MODEL:-claude-3-opus-20240229}"

# Domain adapter configurations
adapters:
  - name: "qa"
    implementation: "retrievers.implementations.qa_chroma_retriever.ChromaRetriever"
    datasource: "chroma"
    adapter: "qa"
    config:
      confidence_threshold: 0.25
      max_context_items: 10
      mode: "simple"

# Datasource configurations
datasources:
  chroma:
    use_local: false
    host: "${CHROMA_HOST:-chroma}"
    port: "${CHROMA_PORT:-8000}"
EOF
    echo "✅ Created example config.yaml"
else
    echo "✅ Found config.yaml"
fi

if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found. Creating example .env file..."
    
    # Create example .env file
    cat > .env << 'EOF'
# ORBIT Docker Environment Variables

# API Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
COHERE_API_KEY=your_cohere_api_key_here

# MongoDB Configuration
MONGODB_URI=mongodb://mongodb:27017/
MONGODB_DB=orbit

# Ollama Configuration
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3

# ChromaDB Configuration
CHROMA_HOST=chroma
CHROMA_PORT=8000

# Admin Token (for API key management)
API_ADMIN_TOKEN=your_admin_token_here
EOF
    echo "✅ Created example .env file"
    echo "⚠️ Please edit the .env file to add your API keys before proceeding."
    exit 1
else
    echo "✅ Found .env file"
fi

# Check if docker-compose.yml exists, if not create it
if [ ! -f "docker-compose.yml" ]; then
    echo "⚠️ docker-compose.yml not found. Creating file..."
    
    cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  orbit:
    image: orbit-server:latest
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - DEPENDENCY_PROFILE=all  # Options: minimal, huggingface, commercial, all
        - INSTALL_EXTRA_DEPS=false
    container_name: orbit-server
    depends_on:
      - mongodb
      - ollama
      - chroma
    ports:
      - "3000:3000"
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
      - ./data:/app/data
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - OLLAMA_MODEL=llama3
      - MONGODB_URI=mongodb://mongodb:27017/
      - MONGODB_DB=orbit
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  mongodb:
    image: mongo:6
    container_name: orbit-mongodb
    volumes:
      - mongodb_data:/data/db
    ports:
      - "27017:27017"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  ollama:
    image: ollama/ollama:latest
    container_name: orbit-ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  chroma:
    image: chromadb/chroma:latest
    container_name: orbit-chroma
    volumes:
      - chroma_data:/chroma/chroma
    ports:
      - "8000:8000"
    environment:
      - ALLOW_RESET=true
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  mongodb_data:
  ollama_data:
  chroma_data:
EOF
    echo "✅ Created docker-compose.yml"
fi

# Check if Dockerfile exists, if not create it
if [ ! -f "Dockerfile" ] || [ "$REBUILD_IMAGE" = true ]; then
    echo "⚠️ Creating new Dockerfile..."
    
    cat > Dockerfile << 'EOF'
FROM python:3.12-slim

# Build arguments for dependency profiles
ARG DEPENDENCY_PROFILE=minimal
ARG INSTALL_EXTRA_DEPS=false

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies file
COPY dependencies.toml .

# Install Python dependencies based on profile
RUN pip install --no-cache-dir \
    # Core dependencies (minimal profile)
    fastapi>=0.115.9 \
    uvicorn==0.34.2 \
    python-dotenv==1.0.1 \
    requests==2.31.0 \
    psutil==6.0.0 \
    motor>=3.7.0 \
    pymongo>=4.12.0 \
    chromadb>=1.0.9 \
    langchain-ollama>=0.2.3 \
    langchain-community>=0.0.10 \
    aiohttp>=3.11.1 \
    ollama==0.4.8 \
    redis>=6.1.0 \
    pydantic>=2.10.0 \
    PyYAML>=6.0.1 \
    python-multipart>=0.0.14 \
    langid==1.1.6 \
    pycld2==0.42 \
    langdetect>=1.0.9 \
    python-json-logger>=2.0.7 \
    tqdm>=4.66.2 \
    aiodns>=3.2.0 \
    regex==2024.11.6 \
    sseclient-py==1.8.0 \
    pycountry>=24.6.1 \
    llama-cpp-python==0.3.9 \
    elasticsearch==9.0.0

# Install Hugging Face dependencies if profile includes it
RUN if [ "$DEPENDENCY_PROFILE" = "huggingface" ] || [ "$DEPENDENCY_PROFILE" = "all" ]; then \
    pip install --no-cache-dir \
    huggingface-hub==0.30.2 \
    safetensors==0.5.3 \
    torch==2.1.0 \
    transformers==4.35.0; \
    fi

# Install commercial provider dependencies if profile includes it
RUN if [ "$DEPENDENCY_PROFILE" = "commercial" ] || [ "$DEPENDENCY_PROFILE" = "all" ]; then \
    pip install --no-cache-dir \
    openai==1.76 \
    anthropic==0.50.0 \
    google-generativeai==0.8.5 \
    cohere==5.15.0 \
    groq==0.23.1 \
    deepseek==1.0.0 \
    mistralai==1.7.0 \
    together==1.5.7 \
    boto3==1.38.13 \
    azure-ai-inference==1.0.0b9; \
    fi

# Install development dependencies if requested
RUN if [ "$INSTALL_EXTRA_DEPS" = "true" ]; then \
    pip install --no-cache-dir \
    pytest>=8.3.5 \
    pytest-asyncio>=0.26.0 \
    pytest-cov>=6.0.0 \
    black>=24.10.0 \
    flake8>=7.1.1 \
    mypy>=1.13.0 \
    pre-commit>=4.0.1; \
    fi

# Copy the rest of the application
COPY server ./server
COPY bin ./bin
COPY config ./config
COPY README.md .

# Create necessary directories
RUN mkdir -p logs data config

# Make scripts executable
RUN chmod +x bin/orbit.py bin/orbit.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV PATH="/app/bin:${PATH}"

# Expose the server port
EXPOSE 3000

# Create entrypoint script
RUN echo '#!/bin/bash' > /app/entrypoint.sh && \
    echo 'set -e' >> /app/entrypoint.sh && \
    echo 'if [ "$1" = "server" ]; then' >> /app/entrypoint.sh && \
    echo '  exec python server/main.py --config ${CONFIG_PATH:-/app/config/config.yaml}' >> /app/entrypoint.sh && \
    echo 'elif [ "$1" = "cli" ]; then' >> /app/entrypoint.sh && \
    echo '  shift' >> /app/entrypoint.sh && \
    echo '  exec bin/orbit.sh "$@"' >> /app/entrypoint.sh && \
    echo 'else' >> /app/entrypoint.sh && \
    echo '  exec "$@"' >> /app/entrypoint.sh && \
    echo 'fi' >> /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["server"]
EOF
    echo "✅ Created Dockerfile"
fi

# Build or start Docker containers
if [ "$BUILD" = true ]; then
    echo "🔨 Building and starting Docker containers..."
    if [ "$VERBOSE" = true ]; then
        docker compose up -d --build
    else
        docker compose up -d --build > /dev/null 2>&1
    fi
else
    echo "🐳 Starting Docker containers..."
    if [ "$VERBOSE" = true ]; then
        docker compose up -d
    else
        docker compose up -d > /dev/null 2>&1
    fi
fi

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 5

# Display status information
echo "📊 Service status:"
docker compose ps

# Check if services are healthy
echo "🏥 Health status:"
docker ps --format "{{.Names}}: {{.Status}}" | grep orbit

# Check if Ollama has the required model
echo "🧠 Checking if required Ollama models are available..."
OLLAMA_MODEL=$(grep -oP 'model: "\$\{OLLAMA_MODEL:-\K[^}]*' config/config.yaml | sed 's/"}"//')
if [ -z "$OLLAMA_MODEL" ]; then
    OLLAMA_MODEL="llama3"
fi

echo "   - Detected model: $OLLAMA_MODEL"
MODEL_EXISTS=$(docker exec -it orbit-ollama ollama list | grep -c "$OLLAMA_MODEL" || echo "0")
if [ "$MODEL_EXISTS" -eq "0" ]; then
    echo "⚠️ Model $OLLAMA_MODEL not found in Ollama. Pulling model..."
    docker exec -it orbit-ollama ollama pull $OLLAMA_MODEL
else
    echo "✅ Model $OLLAMA_MODEL is already available"
fi

echo "
🎉 ORBIT Docker environment initialized successfully!

To interact with your ORBIT system:

1. Server is accessible at: http://localhost:3000
2. API endpoints:
   - Chat: POST http://localhost:3000/v1/chat
   - Health: GET http://localhost:3000/health

3. Use the CLI inside the container:
   docker exec -it orbit-server orbit status
   docker exec -it orbit-server orbit key list

4. For logs, check:
   docker compose logs -f orbit-server
   or check the 'logs' directory

Management Commands:
- Shut down:    docker compose down
- Restart:      docker compose restart
- Rebuild:      ./docker-init.sh --rebuild-image

Happy orbiting! 🚀
"
