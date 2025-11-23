FROM python:3.12-slim

# Build arguments for dependency profiles
# Empty means default dependencies only, specify profile (e.g., torch, cloud) to add additional dependencies
ARG DEPENDENCY_PROFILE=

WORKDIR /orbit

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
COPY install/dependencies.toml /orbit/install/
COPY install/generate_requirements.py /orbit/install/

# Copy setup script and make it executable
COPY install/setup.sh /orbit/install/
RUN chmod +x /orbit/install/setup.sh

# Install Python dependencies based on profile
# First install core dependencies that are always needed
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install tomli for TOML parsing (needed by generate_requirements.py)
RUN pip install --no-cache-dir tomli

# Generate requirements file from TOML and install dependencies
# If DEPENDENCY_PROFILE is empty, use default dependencies only
RUN cd /orbit/install && \
    if [ -z "${DEPENDENCY_PROFILE}" ]; then \
        python3 generate_requirements.py --output /tmp/requirements.txt; \
    else \
        python3 generate_requirements.py "${DEPENDENCY_PROFILE}" --output /tmp/requirements.txt; \
    fi && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy the application code
COPY server/ /orbit/server/
COPY bin/ /orbit/bin/
COPY LICENSE* /orbit/

# Copy default-config as config directory
COPY install/default-config/ /orbit/config/

# Make scripts executable
RUN chmod +x /orbit/bin/orbit.py /orbit/bin/orbit.sh

# Create necessary directories
RUN mkdir -p /orbit/logs /orbit/data /orbit/models /orbit/gguf

# Set environment variables
ENV PYTHONPATH=/orbit
ENV PATH="/orbit/bin:${PATH}"

# Expose the server port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

# Run the server with configurable config path
CMD ["sh", "-c", "python /orbit/server/main.py --config ${CONFIG_PATH:-/orbit/config/config.yaml}"]