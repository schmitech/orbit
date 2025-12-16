# ORBIT Basic Docker Image - Quick Start Guide

This guide will help you get started with the ORBIT basic Docker image - a minimal, self-contained image perfect for testing and onboarding new users.

## What's Included

The basic image contains:
- **ORBIT server** with core functionality
- **orbitchat web app** - browser-based chat interface (no installation needed!)
- **simple-chat adapter** - a conversational chatbot adapter
- **Ollama** with pre-pulled models:
  - **granite4:1b** - chat/inference model
  - **nomic-embed-text** - embeddings model
- **Default database** - pre-configured so no API key creation needed
- **Default configuration** - optimized for quick start

No API keys or external services required - just pull and run!

## Prerequisites

- **Docker** (version 20.10 or higher)
- **4GB+ RAM** available for Docker
- **2GB+ disk space** for the image

## Quick Start

### 1. Pull the Image

```bash
docker pull schmitech/orbit:basic
```

Or use the latest tag:
```bash
docker pull schmitech/orbit:latest
```

### 2. Run the Container

```bash
docker run -d \
  --name orbit-basic \
  -p 5173:5173 \
  -p 3000:3000 \
  schmitech/orbit:basic
```

This exposes:
- **Port 5173** - orbitchat web app (open in your browser)
- **Port 3000** - ORBIT API (used by the web app)

### 3. Open the Web App

Open your browser and go to:
```
http://localhost:5173
```

You can start chatting immediately - no setup required!

**Note:** The `ORBIT_DEFAULT_ADMIN_PASSWORD` environment variable is optional. If not set, it defaults to `admin123`. It's only needed if you want to use CLI commands (like creating API keys). The API works without authentication for the simple-chat adapter.

### 4. Verify It's Running (Optional)

Check the container status:
```bash
docker ps | grep orbit-basic
```

Test the health endpoint:
```bash
curl http://localhost:3000/health
```

You should see a response indicating the server is healthy.

### 5. Test the API (Optional)

Make a simple chat request:
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

## Configuration

### Environment Variables

Optional environment variables:
- `ORBIT_DEFAULT_ADMIN_PASSWORD` - Admin password for CLI access (default: `admin123` if not set)
  - Only needed if you want to use CLI commands (login, creating API keys, etc.)
  - The API works without authentication for the simple-chat adapter

### Persistent Data

To persist data across container restarts, mount volumes:

```bash
docker run -d \
  --name orbit-basic \
  -p 5173:5173 \
  -p 3000:3000 \
  -v orbit-data:/orbit/data \
  -v orbit-logs:/orbit/logs \
  schmitech/orbit:basic
```

Or with a custom admin password (only needed for CLI access):
```bash
docker run -d \
  --name orbit-basic \
  -p 5173:5173 \
  -p 3000:3000 \
  -e ORBIT_DEFAULT_ADMIN_PASSWORD=your-secure-password \
  -v orbit-data:/orbit/data \
  -v orbit-logs:/orbit/logs \
  schmitech/orbit:basic
```

## Using the CLI

### Using the Helper Script (Recommended)

The easiest way to use the CLI is with the `orbit-docker.sh` helper script:

```bash
# Login as admin (will prompt for password, default: admin123)
./docker/orbit-docker.sh --container orbit-basic login

# Create a default API key with a simple prompt (using --prompt-text)
./docker/orbit-docker.sh --container orbit-basic cli key create \
  --adapter simple-chat \
  --name "Default Chat Key" \
  --prompt-name "Default Assistant Prompt" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."

# Or create a key with a prompt from a file
./docker/orbit-docker.sh --container orbit-basic cli key create \
  --adapter simple-chat \
  --name "My App Key" \
  --prompt-name "Custom Prompt" \
  --prompt-file /path/to/prompt.txt

# List API keys
./docker/orbit-docker.sh --container orbit-basic cli key list

# Check status
./docker/orbit-docker.sh --container orbit-basic status
```

### Direct Docker Exec

You can also access the CLI directly:

```bash
# Login as admin
docker exec -it orbit-basic python /orbit/bin/orbit.py login --username admin

# Create an API key with a simple prompt (using --prompt-text)
docker exec -it orbit-basic python /orbit/bin/orbit.py key create \
  --adapter simple-chat \
  --name "Default Key" \
  --prompt-name "Default Prompt" \
  --prompt-text "You are a helpful assistant. Be concise and friendly."

# Create an API key without a prompt
docker exec -it orbit-basic python /orbit/bin/orbit.py key create \
  --adapter simple-chat \
  --name "My App"

# List API keys
docker exec -it orbit-basic python /orbit/bin/orbit.py key list
```

**Note:** The CLI supports both `--prompt-text` (direct string) and `--prompt-file` (file path). Use `--prompt-text` for simple prompts, and `--prompt-file` for longer prompts stored in files.

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

### With Custom API Key

To create and use your own API key using the CLI:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_your-key-here' \
  -H 'X-Session-ID: my-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "What is ORBIT?"}
    ],
    "stream": false
  }'
```

## Stopping the Container

```bash
# Stop the container
docker stop orbit-basic

# Remove the container
docker rm orbit-basic
```

## Troubleshooting

### Container Won't Start

Check the logs:
```bash
docker logs orbit-basic
```

### Port Already in Use

Use different ports:
```bash
docker run -d \
  --name orbit-basic \
  -p 5174:5173 \
  -p 3001:3000 \
  schmitech/orbit:basic
```

Then access the web app at `http://localhost:5174`

### Out of Memory

Increase Docker's memory limit in Docker Desktop settings, or ensure you have at least 4GB RAM available.

### Model Not Found

The model should be included in the image. If you see errors about missing models, check:
```bash
docker exec orbit-basic ollama list
```

You should see `granite4:1b` and `nomic-embed-text` in the output. If not, you can pull them manually:
```bash
docker exec orbit-basic ollama pull granite4:1b
docker exec orbit-basic ollama pull nomic-embed-text:latest
```

## What's Different from the Full Image?

The basic image is optimized for simplicity:
- **Includes orbitchat web app** - ready-to-use browser interface, no npm install needed
- **Only simple-chat adapter** - no file uploads, no retrieval, just chat
- **Pre-included Ollama + model** - granite4:1b is pre-pulled in the image
- **Default database included** - no need to create API keys to get started
- **Default dependencies only** - no cloud SDKs or extra packages

For full functionality (file uploads, multiple adapters, etc.), use the standard ORBIT Docker setup as described in the main README.

## Building and Publishing the Basic Image

If you want to build and publish your own basic Docker image, follow these steps:

### Prerequisites for Building

- **Docker** (version 20.10 or higher)
- **Git** (to clone the repository)
- **Docker Hub account** (if publishing)
- **12GB+ disk space** (for the build process, Node.js, orbitchat, and model download)

### Step-by-Step Instructions

#### 1. Clone the Repository

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit
```

#### 2. Navigate to Docker Directory

```bash
cd docker
```

#### 3. Make the Publish Script Executable

```bash
chmod +x publish-basic.sh
```

#### 4. Build the Image

Build the Docker image locally:

```bash
./publish-basic.sh --build
```

This will:
- Install Node.js and orbitchat web app
- Install Ollama in the image
- Pull the granite4:1b model (chat) and nomic-embed-text (embeddings)
- Copy the default database (orbit.db)
- Build the Docker image
- Tag it as `schmitech/orbit:basic` and `schmitech/orbit:latest`

**Note:** The first build may take 15-30 minutes depending on your internet connection, as it needs to:
- Install system dependencies
- Install Node.js and orbitchat
- Install Python packages
- Install Ollama and pull the models

#### 5. Test the Image Locally

Before publishing, test the image:

```bash
# Run the container
docker run -d \
  --name orbit-basic-test \
  -p 5173:5173 \
  -p 3000:3000 \
  schmitech/orbit:basic

# Wait for startup (Ollama and services need time to initialize)
sleep 30

# Test the health endpoint
curl http://localhost:3000/health

# Open the web app in your browser
open http://localhost:5173  # macOS
# or: xdg-open http://localhost:5173  # Linux
# or manually open http://localhost:5173 in your browser

# (Optional) Test the API directly
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

# Clean up
docker stop orbit-basic-test
docker rm orbit-basic-test
```

#### 6. Login to Docker Hub (if Publishing)

If you want to publish to Docker Hub:

```bash
docker login
```

Enter your Docker Hub username and password when prompted.

#### 7. Publish to Docker Hub

Publish the image with the default tags:

```bash
./publish-basic.sh --publish
```

Or publish with a version tag:

```bash
./publish-basic.sh --publish --tag v1.0.0
```

This will:
- Build the image (if not already built)
- Push `schmitech/orbit:basic`
- Push `schmitech/orbit:latest`
- Push `schmitech/orbit:basic-v1.0.0` (if `--tag` is specified)

### Build Script Options

The `publish-basic.sh` script supports the following options:

```bash
# Build only (no publish)
./publish-basic.sh --build

# Build and publish
./publish-basic.sh --publish

# Build and publish with version tag
./publish-basic.sh --publish --tag v1.0.0

# Show help
./publish-basic.sh --help
```

### Troubleshooting the Build

#### Build Fails with Missing Config Files

Ensure the required configuration files exist:

```bash
ls install/default-config/ollama.yaml
ls install/default-config/inference.yaml
ls install/orbit.db.default
```

#### Ollama Model Pull Fails

If the model pull fails during build:

1. Check your internet connection
2. The build starts Ollama temporarily to pull the model
3. You can test Ollama manually: `ollama pull granite4:1b`

#### Docker Build Runs Out of Memory

If the build fails due to memory issues:

1. Increase Docker's memory limit in Docker Desktop settings
2. Close other applications to free up RAM
3. The build process needs at least 4GB RAM available

#### Image Size is Very Large

The basic image should be around 4-5GB including Node.js, orbitchat, Ollama, and the models. If it's significantly larger:

1. Check that you're using `Dockerfile.basic` (not the full Dockerfile)
2. Ensure you're not including unnecessary files

## Next Steps

Once you're comfortable with the basic image, you can:
1. Explore the full ORBIT capabilities using the standard Docker setup
2. Customize the configuration for your needs
3. Add additional adapters and models
4. Integrate with your applications

For more information, see the main [README.md](README.md).

Happy Orbiting! 🚀

