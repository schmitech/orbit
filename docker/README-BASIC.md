# ORBIT Basic Docker Image - Quick Start Guide

This guide will help you get started with the ORBIT basic Docker image - a minimal, self-contained image perfect for testing and onboarding new users.

## What's Included

The basic image contains:
- **ORBIT server** with core functionality
- **simple-chat adapter** - a conversational chatbot adapter
- **gemma3-1b model** - pre-downloaded and ready to use
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
  -p 3000:3000 \
  schmitech/orbit:basic
```

**Note:** The `ORBIT_DEFAULT_ADMIN_PASSWORD` environment variable is optional. If not set, it defaults to `admin123`. It's only needed if you want to use CLI commands (like creating API keys). The API works without authentication for the simple-chat adapter.

### 3. Verify It's Running

Check the container status:
```bash
docker ps | grep orbit-basic
```

Test the health endpoint:
```bash
curl http://localhost:3000/health
```

You should see a response indicating the server is healthy.

### 4. Test the API

Make a simple chat request:
```bash
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
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
  -p 3000:3000 \
  -v orbit-data:/orbit/data \
  -v orbit-logs:/orbit/logs \
  schmitech/orbit:basic
```

Or with a custom admin password (only needed for CLI access):
```bash
docker run -d \
  --name orbit-basic \
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
  -H 'X-Session-ID: my-session' \
  -d '{
    "messages": [
      {"role": "user", "content": "Tell me a short story"}
    ],
    "stream": true
  }' \
  --no-buffer
```

### With API Key

First, create an API key using the CLI (see above), then use it:

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

Use a different port:
```bash
docker run -d \
  --name orbit-basic \
  -p 3001:3000 \
  -e ORBIT_DEFAULT_ADMIN_PASSWORD=admin123 \
  schmitech/orbit:basic
```

Then access at `http://localhost:3001`

### Out of Memory

Increase Docker's memory limit in Docker Desktop settings, or ensure you have at least 4GB RAM available.

### Model Not Found

The model should be included in the image. If you see errors about missing models, check:
```bash
docker exec orbit-basic ls -la /orbit/models/
```

You should see `gemma-3-1b-it-Q4_0.gguf` in the output.

## What's Different from the Full Image?

The basic image is optimized for simplicity:
- **Only simple-chat adapter** - no file uploads, no retrieval, just chat
- **Pre-included model** - gemma3-1b is bundled in the image
- **Default dependencies only** - no cloud SDKs or extra packages
- **Smaller size** - faster to pull and run

For full functionality (file uploads, multiple adapters, etc.), use the standard ORBIT Docker setup as described in the main README.

## Building and Publishing the Basic Image

If you want to build and publish your own basic Docker image, follow these steps:

### Prerequisites for Building

- **Docker** (version 20.10 or higher)
- **Git** (to clone the repository)
- **Docker Hub account** (if publishing)
- **10GB+ disk space** (for the build process and model download)

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

#### 4. (Optional) Pre-download the Model

To avoid downloading the model during each build (saves time when testing), you can pre-download it:

```bash
# Create models directory if it doesn't exist
mkdir -p ../models

# Download the model (if not already present)
python3 ../install/download_hf_gguf_model.py \
  --repo-id "unsloth/gemma-3-1b-it-GGUF" \
  --filename "gemma-3-1b-it-Q4_0.gguf" \
  --output-dir ../models
```

The build script will automatically detect and use the model if it exists in the `models/` directory.

#### 5. Build the Image

Build the Docker image locally:

```bash
./publish-basic.sh --build
```

This will:
- Download the gemma3-1b model (if not already in `models/` directory)
- Build the Docker image
- Tag it as `schmitech/orbit:basic` and `schmitech/orbit:latest`

**Note:** The first build may take 15-30 minutes depending on your internet connection, as it needs to:
- Install system dependencies
- Install Python packages
- Download the GGUF model (~700MB)

#### 6. Test the Image Locally

Before publishing, test the image:

```bash
# Run the container
docker run -d \
  --name orbit-basic-test \
  -p 3000:3000 \
  schmitech/orbit:basic

# Wait a few seconds for startup
sleep 10

# Test the health endpoint
curl http://localhost:3000/health

# (Optional) Create an API key first for authenticated requests
# docker exec -it orbit-basic-test python /orbit/bin/orbit.py login --username admin --password admin123
# docker exec -it orbit-basic-test python /orbit/bin/orbit.py key create \
#   --adapter simple-chat \
#   --name "Test Key" \
#   --prompt-text "You are a helpful assistant."

# Test a chat request (replace 'orbit_your-key-here' with your actual API key)
# Note: API key is optional for simple-chat adapter, but recommended
curl -X POST http://localhost:3000/v1/chat \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: orbit_your-key-here' \
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

#### 7. Login to Docker Hub (if Publishing)

If you want to publish to Docker Hub:

```bash
docker login
```

Enter your Docker Hub username and password when prompted.

#### 8. Publish to Docker Hub

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

#### Build Fails with "No models directory"

The script automatically creates the `models/` directory. If you see this error, ensure you're running from the project root:

```bash
cd /path/to/orbit/docker
./publish-basic.sh --build
```

#### Model Download Fails

If the model download fails during build:

1. Check your internet connection
2. Try pre-downloading the model manually (see step 4 above)
3. Check that `install/gguf-models.json` exists and contains the gemma3-1b entry

#### Docker Build Runs Out of Memory

If the build fails due to memory issues:

1. Increase Docker's memory limit in Docker Desktop settings
2. Close other applications to free up RAM
3. The build process needs at least 4GB RAM available

#### Image Size is Very Large

The basic image should be around 2-3GB including the model. If it's larger:

1. Check that you're using `Dockerfile.basic` (not the full Dockerfile)
2. Ensure you're not including unnecessary files
3. The model file itself is ~700MB, so the image will be at least that size

## Next Steps

Once you're comfortable with the basic image, you can:
1. Explore the full ORBIT capabilities using the standard Docker setup
2. Customize the configuration for your needs
3. Add additional adapters and models
4. Integrate with your applications

For more information, see the main [README.md](README.md).

Happy Orbiting! 🚀

