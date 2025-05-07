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

# Copy requirements and config files
COPY requirements.txt .
COPY config.yaml .

# Create and activate virtual environment
RUN python3 -m venv venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p /app/logs && chown -R orbit:orbit /app

# Switch to non-root user
USER orbit

# Expose port (will be read from config.yaml)
EXPOSE 3000

# Start the application
CMD ["python", "main.py"]