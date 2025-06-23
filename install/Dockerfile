FROM python:3.12-slim

# Build arguments for dependency profiles
ARG DEPENDENCY_PROFILE=minimal

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    gcc \
    g++ \
    make \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency configuration first (for better caching)
COPY install/dependencies.toml /app/install/

# Copy setup script and make it executable
COPY install/setup.sh /app/install/
RUN chmod +x /app/install/setup.sh

# Install Python dependencies based on profile
# First install core dependencies that are always needed
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies from dependencies.toml based on profile
COPY install/requirements-${DEPENDENCY_PROFILE}.txt* /tmp/
RUN if [ -f /tmp/requirements-${DEPENDENCY_PROFILE}.txt ]; then \
        pip install --no-cache-dir -r /tmp/requirements-${DEPENDENCY_PROFILE}.txt; \
    else \
        # Fall back to manual installation if requirements file doesn't exist
        pip install --no-cache-dir \
        setuptools>=70.0.0 \
        ollama==0.5.1 \
        motor>=3.6.0 \
        pymongo>=4.10.1 \
        redis>=5.2.0 \
        chromadb>=0.5.23 \
        qdrant-client>=1.12.1 \
        langchain-ollama>=0.2.3 \
        langchain-community>=0.3.14 \
        pydantic>=2.10.4 \
        jinja2>=3.1.4 \
        PyYAML>=6.0.2 \
        fastapi>=0.115.0 \
        uvicorn==0.32.1 \
        python-dotenv==1.0.1 \
        requests==2.32.3 \
        python-multipart>=0.0.14 \
        langid==1.1.6 \
        pycld2==0.42 \
        langdetect>=1.0.9 \
        pytest>=8.3.4 \
        python-json-logger>=2.0.7 \
        tqdm>=4.67.1 \
        aiohttp>=3.11.11 \
        aiodns>=3.2.0 \
        regex==2024.11.6 \
        sseclient-py==1.8.0 \
        psutil==6.1.1 \
        pycountry>=24.6.1 \
        llama-cpp-python==0.3.9 \
        elasticsearch==9.0.0 \
        pypdf==5.1.0 \
        docx2python==3.5.0 \
        openpyxl>=3.1.5 \
        python-magic>=0.4.27 \
        schmitech-orbit-client==0.2.2; \
    fi

# Install additional dependencies based on profile
RUN if [ "$DEPENDENCY_PROFILE" = "torch" ] || [ "$DEPENDENCY_PROFILE" = "all" ]; then \
        pip install --no-cache-dir \
        torch==2.7.1 \
        vllm>=0.7.1 \
        llm-guard>=0.3.16 \
        transformers>=4.46.3 \
        accelerate>=0.27.2 \
        sentencepiece>=0.2.0 \
        protobuf>=4.25.2; \
    fi

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
        azure-ai-inference==1.0.0b9 \
        google-cloud-aiplatform==1.98.0; \
    fi

# Copy the application code
COPY server/ /app/server/
COPY bin/ /app/bin/
COPY README.md /app/
COPY LICENSE* /app/

# Make scripts executable
RUN chmod +x /app/bin/orbit.py /app/bin/orbit.sh

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/config /app/gguf

# Set environment variables
ENV PYTHONPATH=/app
ENV PATH="/app/bin:${PATH}"

# Expose the server port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

# Run the server with configurable config path
CMD ["sh", "-c", "python /app/server/main.py --config ${CONFIG_PATH:-/app/config.yaml}"]