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
COPY install/generate_requirements.py /app/install/

# Copy setup script and make it executable
COPY install/setup.sh /app/install/
RUN chmod +x /app/install/setup.sh

# Install Python dependencies based on profile
# First install core dependencies that are always needed
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install tomli for TOML parsing (needed by generate_requirements.py)
RUN pip install --no-cache-dir tomli

# Generate requirements file from TOML and install dependencies
RUN cd /app/install && \
    python3 generate_requirements.py ${DEPENDENCY_PROFILE} /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy the application code
COPY server/ /app/server/
COPY bin/ /app/bin/
COPY LICENSE* /app/

# Copy config directory
COPY config/ /app/config/

# Make scripts executable
RUN chmod +x /app/bin/orbit.py /app/bin/orbit.sh

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/gguf

# Set environment variables
ENV PYTHONPATH=/app
ENV PATH="/app/bin:${PATH}"

# Expose the server port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

# Run the server with configurable config path
CMD ["sh", "-c", "python /app/server/main.py --config ${CONFIG_PATH:-/app/config/config.yaml}"]