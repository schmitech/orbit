# ORBIT Docker - Quick Start Guide

This guide will help you get started with ORBIT using docker-compose. The setup uses separate containers for better isolation, flexibility, and GPU configuration.

## Architecture

```
docker-compose.yml
├── ollama        (official ollama/ollama image, port 11434)
├── ollama-init   (one-shot: pulls smollm2 + nomic-embed-text models)
└── orbit         (lean Python server image, port 3000)
```

- **Ollama** runs in its own container with a persistent volume for models
- **ORBIT server** is a lean Python image (no Ollama, no Node.js bundled)
- **orbitchat** is installed separately on the host via `npm install -g orbitchat`

## What's Included

- **ORBIT server** with core functionality
- **simple-chat adapter** - a conversational chatbot adapter
- **Ollama** (separate container) with auto-pulled models:
  - **smollm2** - chat/inference model (ultra-fast, ~1.2GB)
  - **nomic-embed-text** - embeddings model
- **Default database** - pre-configured so no API key creation needed
- **Default configuration** - optimized for quick start
- **Automatic GPU/CPU detection** - selects optimal preset at runtime

No external API keys or cloud services required!

## Prerequisites

- **Docker** (version 20.10 or higher) with **Docker Compose** v2
- **4GB+ RAM** available for Docker
- **3GB+ disk space** for images and models
- **Node.js** (optional, for orbitchat web interface)

## Quick Start

You can run ORBIT with Docker in two ways:

| Option | Use when |
|--------|----------|
| **Docker Compose** (below) | You want Ollama + models + ORBIT in one go (recommended). |
| **Pre-built image only** | You already have Ollama on the host or elsewhere; you only need the ORBIT server. |

### 1. Start the Services (Docker Compose)

```bash
cd docker
docker compose up -d
```

This starts three containers:
- **ollama** - LLM inference server (port 11434)
- **ollama-init** - pulls required models then exits
- **orbit** - ORBIT API server (port 3000)

### 2. Verify Everything is Running

```bash
# Check container status
docker compose ps
```

You should see `ollama` and `orbit` as healthy, and `ollama-init` as exited (0).

```bash
# Test the health endpoint
curl http://localhost:3000/health

# Verify models are available
curl http://localhost:11434/api/tags
```

### 3. Connect orbitchat (Optional)

Install and run the orbitchat web interface from your host machine:

```bash
npm install -g orbitchat
ORBIT_ADAPTER_KEYS='{"simple-chat":"default-key"}' orbitchat
```

Then open `http://localhost:5173` in your browser.

### 4. Test the API

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: test-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello, what is 2+2?"}
    ],
    "stream": false
  }'
```

### Option B: Pre-built image (single container)

To run only the ORBIT server from Docker Hub (no Ollama or models inside the image):

```bash
docker pull schmitech/orbit:basic
docker run -d --name orbit-basic -p 3000:3000 schmitech/orbit:basic
```

The server will listen on port 3000 but needs an LLM backend to handle chat:

- **Ollama on your host:** use `host.docker.internal` so the container can reach it:
  ```bash
  docker run -d --name orbit-basic -p 3000:3000 \
    -e OLLAMA_HOST=host.docker.internal:11434 \
    schmitech/orbit:basic
  ```
- **Ollama in another container or remote:** set `OLLAMA_HOST` to that address (e.g. `ollama:11434` or `http://your-ollama-host:11434`).

The `basic` image includes the **simple-chat** adapter only. For the full stack (Ollama + model pull + ORBIT), use Docker Compose (Option A above).

## GPU Mode (NVIDIA)

To enable NVIDIA GPU acceleration for Ollama:

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

This requires:
- NVIDIA GPU with compatible drivers
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed

The ORBIT server automatically detects the GPU and selects the appropriate preset (`smollm2-1.7b-gpu` vs `smollm2-1.7b-cpu`).

You can also force a specific preset:

```bash
# In docker-compose.yml, change the orbit service environment:
environment:
  - ORBIT_PRESET=smollm2-1.7b-gpu
```

## Configuration

### Environment Variables

Set these in `docker-compose.yml` under the `orbit` service:

- `ORBIT_PRESET` - Override GPU auto-detection (default: `auto`)
  - `auto` - detect GPU and select appropriate preset
  - `smollm2-1.7b-gpu` - force GPU preset
  - `smollm2-1.7b-cpu` - force CPU preset
  - Any preset name from `ollama.yaml`
- `OLLAMA_HOST` - Ollama service address (default: `ollama:11434`)
- `ORBIT_DEFAULT_ADMIN_PASSWORD` - Admin password for CLI access (default: `admin123`)

### Persistent Data

Docker-compose volumes are configured by default:

- `ollama-data` - Ollama models (persists across restarts, no re-download)
- `orbit-data` - ORBIT application data
- `orbit-logs` - ORBIT server logs

Models are only pulled once by `ollama-init`. Subsequent `docker compose down && docker compose up -d` will reuse cached models.

## Using the CLI

### Using the Helper Script (Recommended)

```bash
# Login as admin (will prompt for password, default: admin123)
./docker/orbit-docker.sh --container orbit-server login

# Create a default API key with a simple prompt
./docker/orbit-docker.sh --container orbit-server cli key create \
  --adapter simple-chat \
  --name "Default Chat Key" \
  --prompt-name "Default Assistant Prompt" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."

# List API keys
./docker/orbit-docker.sh --container orbit-server cli key list

# Check status
./docker/orbit-docker.sh --container orbit-server status
```

### Direct Docker Exec

```bash
# Login as admin
docker exec -it orbit-server python /orbit/bin/orbit.py login --username admin

# Create an API key
docker exec -it orbit-server python /orbit/bin/orbit.py key create \
  --adapter simple-chat \
  --name "Default Key" \
  --prompt-name "Default Prompt" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."

# List API keys
docker exec -it orbit-server python /orbit/bin/orbit.py key list
```

The CLI supports both `--prompt-text` (direct string) and `--prompt-file` (file path).

## API Examples

### Basic Chat Request

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    "stream": false
  }'
```

### Streaming Response

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: default-key' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Tell me a short story"}
    ],
    "stream": true
  }' \
  --no-buffer
```

## Stopping the Services

```bash
cd docker

# Stop all containers
docker compose down

# Stop and remove volumes (deletes models and data)
docker compose down -v
```

## Troubleshooting

### Services Won't Start

Check the logs:
```bash
docker compose logs           # All services
docker compose logs orbit     # ORBIT server only
docker compose logs ollama    # Ollama only
```

### Port Already in Use

Change ports in `docker-compose.yml`:
```yaml
services:
  orbit:
    ports:
      - "3001:3000"   # Use host port 3001 instead
  ollama:
    ports:
      - "11435:11434" # Use host port 11435 instead
```

### Out of Memory

Increase Docker's memory limit in Docker Desktop settings, or ensure at least 4GB RAM is available.

### Models Not Available

The `ollama-init` service pulls models on first start. Check its logs:
```bash
docker compose logs ollama-init
```

If it failed, you can manually pull models:
```bash
docker exec orbit-ollama ollama pull smollm2
docker exec orbit-ollama ollama pull nomic-embed-text:latest
```

### ORBIT Can't Connect to Ollama

Ensure the `ollama` service is healthy:
```bash
docker compose ps
curl http://localhost:11434/api/tags
```

The ORBIT entrypoint waits for Ollama to be ready, but if Ollama takes too long to start, try restarting:
```bash
docker compose restart orbit
```

## Building and Publishing

### Prerequisites for Building

- **Docker** (version 20.10 or higher)
- **Git** (to clone the repository)
- **Docker Hub account** (if publishing)
- **4GB+ disk space** (for the build process - no models bundled in image)

### Build the Image

```bash
cd docker
chmod +x publish.sh

# Build only
./publish.sh --build

# Build and publish to Docker Hub
./publish.sh --publish

# Build and publish with version tag
./publish.sh --publish --tag v1.0.0
```

The build creates a lean server-only image (no Ollama, no Node.js, no models). Models are pulled at runtime by the `ollama-init` service.

### Build Script Options

```bash
./publish.sh --build              # Build the Docker image
./publish.sh --publish            # Build and push to Docker Hub
./publish.sh --publish --tag v1.0.0  # Build, push, and tag version
./publish.sh --help               # Show help
```

### Troubleshooting the Build

**Build fails with missing config files:**
```bash
ls install/default-config/ollama.yaml
ls install/default-config/inference.yaml
ls install/orbit.db.default
```

**Docker build runs out of memory:** Increase Docker's memory limit to at least 4GB.

## Next Steps

Once you're comfortable with the basic setup, you can:
1. Explore the full ORBIT capabilities with additional adapters
2. Customize the configuration for your needs
3. Add more Ollama models by editing the `ollama-init` command
4. Integrate with your applications using the API

For more information, see the main [README.md](../README.md).
