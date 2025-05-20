Orbit uses a TOML file (`dependencies.toml`) to manage different dependency profiles. This approach provides better maintainability and flexibility.

## How to Use

### 1. List Available Profiles

```bash
./setup.sh --list-profiles
```

This shows all available dependency profiles defined in `dependencies.toml`:
- `minimal`: Core dependencies only (default)
- `huggingface`: Adds Hugging Face model support
- `commercial`: Adds commercial cloud providers (OpenAI, Anthropic, etc.)
- `all`: Includes everything
- `development`: Adds development and testing tools

### 2. Install Specific Profile

```bash
# Install minimal dependencies (default)
./setup.sh

# Install Hugging Face support
./setup.sh --profile huggingface

# Install commercial providers
./setup.sh --profile commercial

# Install everything
./setup.sh --profile all
```

### 3. Combine Multiple Profiles

```bash
# Install both Hugging Face and commercial providers
./setup.sh --profile huggingface --profile commercial
```

### 4. Download GGUF Model

```bash
# Install minimal + download GGUF model
./setup.sh --download-gguf

# Install everything + download GGUF model
./setup.sh --profile all --download-gguf
```

## Creating Custom Profiles

You can add custom profiles to `dependencies.toml`:

```toml
[profiles.my_custom]
description = "My custom profile for specific use case"
extends = "minimal"  # Can be a string or array: ["minimal", "commercial"]
dependencies = [
    "openai==1.76",
    "streamlit==1.40.0",
    # Add any specific packages you need
]
```

Then install it:
```bash
./setup.sh --profile my_custom
```

## Profile Inheritance

Profiles can extend other profiles:

```toml
[profiles.data_science]
description = "Data science tools"
extends = ["minimal", "huggingface"]
dependencies = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "scikit-learn>=1.3.0",
    "jupyter>=1.0.0",
]
```

## Model Configuration

GGUF models are configured in the TOML file:

```toml
[models.gguf]
gemma_3_1b = {
    url = "https://huggingface.co/...",
    path = "server/gguf/gemma-3-1b-it-Q4_0.gguf",
    description = "Gemma 3 1B quantized model"
}
```

## 📦 ORBIT Packaging and Distribution Guide

ORBIT includes a build script that creates a distributable tarball containing both the server and CLI components, along with necessary configuration files and documentation.

### Prerequisites for Building

- Bash shell
- Git (optional, for version information)
- Python 3.12 or higher
- `build` and `twine` packages for Python packaging (optional, for PyPI distribution)

### Building Steps

1. Make the build script executable:
   ```bash
   chmod +x build_tarball.sh
   ```

2. Run the build script:
   ```bash
   ./build_tarball.sh
   ```

3. The script will create a distributable tarball at `dist/orbit-0.1.0.tar.gz`

### What's Included in the Package

The distribution package includes:

- **Server Components**: The core ORBIT server implementation
- **CLI Tool**: The orbit.py and orbit.sh scripts for server management
- **Configuration Files**: Example config.yaml and .env files
- **Documentation**: README, quickstart guide, and other documentation
- **Installation Scripts**: Scripts to set up the environment and dependencies

### Installation from the Distribution Package

#### Prerequisites for Installation

Recipients of the distribution package need:

- Python 3.12 or higher
- MongoDB (for API key management)
- Internet connection (for downloading dependencies)

#### Installation Steps

1. Extract the tarball:
   ```bash
   tar -xzf orbit-0.1.0.tar.gz
   cd orbit-0.1.0
   ```

2. Run the installation script:
   ```bash
   ./install.sh
   ```

The installation script will:
- Create a Python virtual environment
- Install required dependencies using setup.sh
- Set up configuration files
- Make the CLI tools executable
- Create symlinks for easy access

#### Post-Installation Configuration

After installation, users should:

1. Edit `config/config.yaml` to configure the server
2. Edit `.env` to set their API keys and other environment variables
3. Start the server with `orbit start`

### Distribution Formats

#### Tarball Distribution (Primary Method)

The tarball distribution is the primary distribution method and works well for most Unix-like systems (Linux, macOS). It preserves all file permissions and directory structures.

#### Alternative Distribution Methods

For specific use cases, consider these alternative distribution methods:

##### Python Package (PyPI)

For Python users familiar with pip, you could create a setuptools-based package:

```bash
# Create a setup.py file
# Build the package
python -m build
# Upload to PyPI
twine upload dist/*
```

This would allow installation via:
```bash
pip install orbit-server
```

##### Docker Container

For containerized deployments, create a Dockerfile with support for different dependency profiles:

```Dockerfile
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
```

Build and distribute as a Docker image with different profiles:

```bash
# Build with minimal dependencies
docker build --build-arg DEPENDENCY_PROFILE=minimal -t orbit-server:0.1.0 .

# Build with Hugging Face support
docker build --build-arg DEPENDENCY_PROFILE=huggingface -t orbit-server:0.1.0 .

# Build with commercial providers
docker build --build-arg DEPENDENCY_PROFILE=commercial -t orbit-server:0.1.0 .

# Build with all dependencies
docker build --build-arg DEPENDENCY_PROFILE=all -t orbit-server:0.1.0 .

# Build with development dependencies
docker build --build-arg DEPENDENCY_PROFILE=all --build-arg INSTALL_EXTRA_DEPS=true -t orbit-server:0.1.0 .
```

For Docker Compose deployments, you can specify the profile in your `docker-compose.yml`:

```yaml
services:
  orbit:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        - DEPENDENCY_PROFILE=all  # Options: minimal, huggingface, commercial, all
        - INSTALL_EXTRA_DEPS=false
```

### Versioning and Updates

For versioning:

1. Update the VERSION variable in build_tarball.sh
2. Document changes in a CHANGELOG.md file
3. Tag the Git repository with the version number

For updates, consider providing:
- An update script that preserves user configurations
- Migration guides for major version changes
- A method to backup and restore user data

### Security Considerations

When distributing the package:

- Never include real API keys or credentials in the distribution
- Use example configurations with placeholders
- Document security best practices
- Encourage users to review permissions and access controls
- Recommend HTTPS for production deployments

## 📦 Creating Distribution Package

To create a distributable tarball for ORBIT:

1. Run the build script:
   ```bash
   ./build-tarball.sh
   ```

2. The script will automatically:
   - Create the distribution package
   - Generate a SHA256 checksum
   - Verify the package contents
   - Create the tarball at `dist/orbit-0.1.0.tar.gz`

The distribution package includes:
- Server components
- CLI tools
- Configuration files
- Documentation
- Installation scripts
- Sample database setup script

## 🚀 Quick Start with Distribution Package

1. Download the latest release tarball from GitHub

2. Extract the package:
   ```bash
   tar -xzf orbit-0.1.0.tar.gz
   cd orbit-0.1.0
   ```

3. Run the installation script:
   ```bash
   ./install.sh
   ```

4. Set up a sample database (optional):
   ```bash
   # For SQLite backend
   ./sample-db-setup.sh sqlite
   
   # For Chroma backend
   ./sample-db-setup.sh chroma
   ```

5. Start the server:
   ```bash
   orbit start
   ```

# ORBIT Installation Guide

## Installation Options

The installation script (`install.sh`) supports different dependency profiles to suit your needs:

```bash
# Show help and available options
./install.sh --help

# Install with minimal profile (default)
./install.sh

# Install with specific profile
./install.sh --profile all
./install.sh -p commercial
./install.sh --profile huggingface
```

### Available Profiles

- `minimal`: Core dependencies only (default)
- `huggingface`: Adds Hugging Face model support
- `commercial`: Adds commercial cloud providers (OpenAI, Anthropic, etc.)
- `all`: Includes everything
- `development`: Adds development and testing tools

### Examples

```bash
# Install minimal dependencies (default)
./install.sh

# Install Hugging Face support
./install.sh --profile huggingface

# Install commercial providers
./install.sh --profile commercial

# Install everything
./install.sh --profile all
```

## Post-Installation Steps

After installation:

1. Edit `config/config.yaml` to configure your server
2. Edit `.env` to set your API keys and other environment variables
3. Start the server with `orbit start`

## Troubleshooting

If you encounter any issues during installation:

1. Ensure Python 3.12 or higher is installed
2. Check that all required system dependencies are installed
3. Verify your internet connection for downloading packages
4. Check the installation logs for specific error messages