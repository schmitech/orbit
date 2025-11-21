# Docker Basic Image Publishing Plan

## Overview

Create a minimal, ready-to-use Docker image containing only the `simple-chat` and `simple-chat-with-files` adapters, and publish it to Docker Hub under the `schmitech` account.

## Implementation Steps

### 1. Create Minimal Configuration for Basic Image

- **File**: `docker/config-basic.yaml`
- Create a minimal config that imports only necessary adapter files
- Enable only `simple-chat` and `simple-chat-with-files` adapters
- Disable all other adapters in the imported YAML files
- Use cloud profile dependencies (needed for OpenAI embeddings/vision)
- Set sensible defaults for the two adapters

### 2. Create Basic Dockerfile

- **File**: `docker/Dockerfile.basic`
- Base on existing `docker/Dockerfile` but optimized for basic use case
- Use `--profile cloud` for dependencies (OpenAI SDK needed)
- Copy only necessary config files (minimal config + the two adapter YAML files)
- Include entrypoint script that uses the basic config
- Smaller image size by excluding unused adapters/configs

### 3. Create Build and Publish Script

- **File**: `docker/publish-basic.sh`
- Build the basic Docker image with proper tagging
- Tag as `schmitech/orbit:basic` and `schmitech/orbit:latest` (or user preference)
- Push to Docker Hub
- Include error handling and authentication checks
- Support version tagging (e.g., `schmitech/orbit:basic-v1.0.0`)

### 4. Create Minimal Adapter Config Files

- **Files**: 
- `docker/config/adapters/passthrough-basic.yaml` - Only `simple-chat` enabled
- `docker/config/adapters/multimodal-basic.yaml` - Only `simple-chat-with-files` enabled
- These will be copied into the image instead of the full adapter configs

### 5. Create Quick Start Documentation

- **File**: `docker/README-BASIC.md`
- Quick start guide for pulling and running the basic image
- Instructions for setting up API keys
- Example docker-compose.yml for the basic image
- Example API requests to test both adapters

### 6. Update Main README

- **File**: `docker/README.md`
- Add section about the basic image
- Link to quick start guide
- Include Docker Hub pull command

## Files to Create/Modify

### New Files:

1. `docker/Dockerfile.basic` - Optimized Dockerfile for basic image
2. `docker/config-basic.yaml` - Minimal config with only two adapters
3. `docker/config/adapters/passthrough-basic.yaml` - Only simple-chat
4. `docker/config/adapters/multimodal-basic.yaml` - Only simple-chat-with-files  
5. `docker/publish-basic.sh` - Build and publish script
6. `docker/README-BASIC.md` - Quick start guide
7. `docker/docker-compose.basic.yml` - Example compose file for basic image

### Modified Files:

1. `docker/README.md` - Add basic image section

## Key Configuration Details

### Adapters to Enable:

- `simple-chat` (from passthrough.yaml)
- Uses: ollama_cloud, glm-4.6
- No additional dependencies beyond cloud profile

- `simple-chat-with-files` (from multimodal.yaml)
- Uses: ollama_cloud, glm-4.6, openai (embeddings), openai (vision)
- Requires cloud profile for OpenAI SDK

### Dependencies:

- Use `--profile cloud` to include OpenAI SDK
- Default profile includes core dependencies

### Environment Variables Needed:

- `OPENAI_API_KEY` (for embeddings and vision in simple-chat-with-files)
- `OLLAMA_CLOUD_API_KEY` (for inference)
- `ORBIT_DEFAULT_ADMIN_PASSWORD` (for admin access)

## Publishing Workflow

1. Build image: `./docker/publish-demo.sh --build`

- Downloads granite4-micro GGUF model during build
- Creates optimized demo image

2. Test locally: `docker run -p 3000:3000 schmitech/orbit:demo`

- No API keys needed - completely self-contained!
- Just pull and run

3. Publish: `./docker/publish-demo.sh --publish`
4. Tag version: `./docker/publish-demo.sh --publish --tag v1.0.0`

## API Key Configuration

The demo image will automatically create this API key on first startup:

- `default-key` → associated with `simple-chat` adapter

Key is created using the orbit CLI inside the container during initialization.
No external API keys required - the image is fully self-contained with local GGUF model inference.

## Testing Checklist

- [ ] Image builds successfully
- [ ] Container starts and health check passes
- [ ] `simple-chat` adapter works via API
- [ ] `simple-chat-with-files` adapter works with file upload
- [ ] Image size is reasonable (< 2GB ideally)
- [ ] Documentation is clear for new users