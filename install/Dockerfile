FROM python:3.12-slim

# Install system dependencies including git and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    cmake \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash orbit
WORKDIR /app

# Copy dependency management files and config
COPY dependencies.toml .
COPY setup.sh .
COPY config.yaml .

# Make setup script executable
RUN chmod +x setup.sh

# Create and activate virtual environment
RUN python3 -m venv venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip

# Install TOML parser
RUN pip install tomli

# Install Python dependencies using setup.sh
RUN ./setup.sh --profile all

# Create necessary directories
RUN mkdir -p /app/gguf /app/logs

# Copy GGUF model first
COPY gguf/gemma-3-1b-it-Q4_0.gguf /app/gguf/

# Copy application code
COPY . .

# Set proper permissions
RUN chown -R orbit:orbit /app

# Switch to non-root user
USER orbit

# Expose port (will be read from config.yaml)
EXPOSE 3000

# Start the application
CMD ["python", "main.py"]