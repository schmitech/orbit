# ORBIT Demo Image - Quick Start Guide

The ORBIT demo image is a self-contained Docker image that includes everything you need to test ORBIT in minutes - no external API keys or installations required!

## Features

- **Self-contained**: Includes local GGUF model (granite4-micro) - no external APIs needed
- **Pre-configured**: API key (`default-key`) is automatically created on first startup
- **Ready to use**: Just pull and run - no configuration needed
- **Minimal**: Only includes the `simple-chat` adapter for conversational AI
- **Lightweight**: Uses minimal dependencies (~22 packages vs 88+ in full image) for smaller image size

## Building the Image

If you want to build the demo image yourself (instead of pulling from Docker Hub):

### Prerequisites

- Docker installed and running
- Git repository cloned
- ~2GB free disk space (for the image and model)

### Build Instructions

From the project root directory:

```bash
# Navigate to docker directory
cd docker

# Build the image locally
./publish-demo.sh --build
```

This will:
- Build the Docker image with tag `schmitech/orbit:demo`
- Download the granite4-micro GGUF model during build (~500MB)
- Install minimal dependencies (~22 packages)
- Set up the demo configuration

### Build Options

```bash
# Build without using cache (clean build)
./publish-demo.sh --build --no-cache

# Build and publish to Docker Hub (requires login)
./publish-demo.sh --publish

# Build, publish, and tag with version
./publish-demo.sh --publish --tag v1.0.0
```

### Manual Build (Alternative)

If you prefer to use `docker build` directly:

```bash
# From project root
docker build -f docker/Dockerfile.demo -t schmitech/orbit:demo .
```

**Note:** The build context must be the project root (`.`), not the `docker/` directory, because the Dockerfile copies files from the parent directory.

---

## Quick Start (Using Pre-built Image)

### 1. Pull the Image

```bash
docker pull schmitech/orbit:demo
```

### 2. Run the Container

```bash
docker run -d \
  --name orbit-demo \
  -p 3000:3000 \
  schmitech/orbit:demo
```

### 3. Test the API

Wait a few seconds for the server to start, then test it:

```bash
# Check health
curl http://localhost:3000/health

# Test chat (replace YOUR_API_KEY with the key from logs)
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -H 'X-Session-ID: test-session' \
  -d '{
    "message": "Hello! What can you do?",
    "stream": false
  }'
```

## Using Docker Compose

Create a `docker-compose.yml` file:

```yaml
services:
  orbit-demo:
    image: schmitech/orbit:demo
    container_name: orbit-demo
    ports:
      - "3000:3000"
    environment:
      - ORBIT_DEFAULT_ADMIN_PASSWORD=your-password-here
    restart: unless-stopped
```

Then run:

```bash
docker-compose up -d
```

## Getting Your API Key

The `default-key` API key is automatically created on first startup. To retrieve it:

### Option 1: Check Container Logs

```bash
docker logs orbit-demo | grep -i "api key\|default-key"
```

### Option 2: Use the CLI

```bash
# Login as admin (default password: admin123)
docker exec -it orbit-demo /app/bin/orbit.sh auth login --username admin

# List API keys
docker exec -it orbit-demo /app/bin/orbit.sh key list
```

## Example API Requests

### Basic Chat

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_YOUR_KEY_HERE' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "message": "Explain quantum computing in simple terms",
    "stream": false
  }'
```

### Streaming Chat

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_YOUR_KEY_HERE' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "message": "Write a short story about a robot",
    "stream": true
  }'
```

## Configuration

The demo image uses minimal configuration optimized for testing:

- **Inference Provider**: `llama_cpp` (local GGUF model)
- **Model**: `granite-4.0-micro-Q4_0.gguf` (included in image)
- **Adapter**: `simple-chat` (conversational, no retrieval)
- **Database**: SQLite (no external database needed)
- **Port**: 3000

## Environment Variables

Optional environment variables:

- `ORBIT_DEFAULT_ADMIN_PASSWORD`: Admin password (default: `admin123`)
- `ORBIT_PORT`: Server port (default: `3000`)

## Persisting Data

To persist data and logs between container restarts:

```bash
docker run -d \
  --name orbit-demo \
  -p 3000:3000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  schmitech/orbit:demo
```

## Troubleshooting

### Container Won't Start

Check the logs:

```bash
docker logs orbit-demo
```

### Health Check Failing

Wait a bit longer - the model needs time to load on first startup (30-60 seconds).

### API Key Not Working

1. Check that the key was created: `docker logs orbit-demo | grep default-key`
2. Verify you're using the correct format: `orbit_...` or `api_...`
3. Make sure you're including the `X-API-Key` header

### Model Loading Issues

The GGUF model is included in the image, but if you see model loading errors:

1. Check available disk space: `docker system df`
2. Verify model file exists: `docker exec orbit-demo ls -lh /app/models/`
3. Check container resources: `docker stats orbit-demo`

### Useful Debugging Commands

#### Container Management

```bash
# Stop the container
docker stop orbit-demo

# Remove the container
docker rm orbit-demo

# Stop and remove in one command
docker stop orbit-demo 2>/dev/null; docker rm orbit-demo 2>/dev/null

# Remove container even if running (force)
docker rm -f orbit-demo

# Check if container is running
docker ps | grep orbit-demo

# List all containers (including stopped)
docker ps -a | grep orbit-demo
```

#### Check Container Status

```bash
# Check container logs (last 50 lines)
docker logs orbit-demo --tail 50

# Follow logs in real-time
docker logs orbit-demo -f

# Check container resource usage
docker stats orbit-demo --no-stream
```

#### Authentication and API Keys

```bash
# Check authentication status
docker exec orbit-demo /app/bin/orbit.sh auth-status

# Login as admin (interactive)
docker exec -it orbit-demo /app/bin/orbit.sh login --username admin

# Login as admin (non-interactive, using default password)
docker exec orbit-demo bash -c "echo 'admin123' | /app/bin/orbit.sh login --username admin --password-stdin"

# Register admin user (if needed)
docker exec orbit-demo /app/bin/orbit.sh register --username admin --password admin123 --role admin

# List all API keys
docker exec orbit-demo /app/bin/orbit.sh key list

# List API keys (JSON format)
docker exec orbit-demo /app/bin/orbit.sh key list --output json

# Create API key manually
docker exec orbit-demo /app/bin/orbit.sh key create --adapter simple-chat --name default-key

# Test an API key
docker exec orbit-demo /app/bin/orbit.sh key test --key orbit_YOUR_KEY_HERE
```

#### Server and Configuration

```bash
# Check server status
docker exec orbit-demo /app/bin/orbit.sh status

# Test health endpoint from inside container
docker exec orbit-demo curl -f http://localhost:3000/health

# Check configuration
docker exec orbit-demo cat /app/config/config.yaml | head -20

# Check if model file exists
docker exec orbit-demo ls -lh /app/models/

# Check database file
docker exec orbit-demo ls -lh /app/data/
```

#### System Information

```bash
# Check Python version
docker exec orbit-demo python3 --version

# Check installed packages
docker exec orbit-demo pip list | grep -E "llama|fastapi|uvicorn"

# Check disk usage
docker exec orbit-demo df -h

# Check memory usage
docker stats orbit-demo --no-stream

# Check environment variables
docker exec orbit-demo env | grep ORBIT
```

#### Interactive Shell Access

```bash
# Open bash shell in container
docker exec -it orbit-demo bash

# Run Python interactive shell
docker exec -it orbit-demo python3

# Check running processes
docker exec orbit-demo ps aux
```

#### Common Issues and Fixes

**Issue: "bc: command not found"**
- The `bc` package is required by orbit.sh
- Solution: Rebuild the image (already included in latest Dockerfile)

**Issue: "No module named 'X'"**
- Missing Python dependency
- Solution: Add the missing package to `docker/requirements-demo.txt` and rebuild

**Issue: "Failed to initialize services"**
- Check logs for specific service error
- Common causes: missing dependencies, config errors, model file issues

**Issue: API key creation fails**
- Ensure you're authenticated as admin
- Check logs: `docker logs orbit-demo | grep -i "auth\|key"`
- Try manual creation: `docker exec orbit-demo /app/bin/orbit.sh key create --adapter simple-chat --name default-key`

**Issue: Server starts but API returns errors**
- Check if llama_cpp provider is registered: `docker logs orbit-demo | grep -i "llama_cpp"`
- Verify model file exists: `docker exec orbit-demo ls -lh /app/models/granite-4.0-micro-Q4_0.gguf`
- Check inference config: `docker exec orbit-demo cat /app/config/inference.yaml | grep -A 10 llama_cpp`

## What's Included

- **ORBIT Server**: Full ORBIT server with minimal configuration
- **GGUF Model**: granite4-micro model (~500MB) included in image
- **Dependencies**: All required Python packages (llama-cpp-python, etc.)
- **API Key**: Pre-configured `default-key` for immediate use

## What's NOT Included

- External API providers (OpenAI, Anthropic, etc.)
- File upload/retrieval adapters
- Vector database integrations
- Advanced features (reranking, moderation, etc.)

These can be added by using the full ORBIT image or building a custom image.

## Next Steps

Once you've tested the demo:

1. **Explore the API**: Try different prompts and see how the model responds
2. **Check Documentation**: See the main [README.md](README.md) for full features
3. **Build Custom Image**: Create your own image with additional adapters
4. **Deploy**: Use the demo as a starting point for your deployment

## Support

- **GitHub**: [https://github.com/schmitech/orbit](https://github.com/schmitech/orbit)
- **Issues**: Report issues on GitHub
- **Documentation**: See the main [README.md](README.md) for full documentation

Happy testing! 🚀

