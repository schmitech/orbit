# Docker Basic Image Publishing Plan

## Overview

Create a minimal, ready-to-use Docker image following the same packaging strategy as `build-tarball.sh`. The image will use `default-config` directly (copied as `config`), include only the `simple-chat` adapter, and bundle the `granite4:1b` model for a self-contained experience that new users can pull and run immediately.

## Implementation Steps

### 1. Create Basic Dockerfile

- **File**: `docker/Dockerfile.basic`
- Base on existing `docker/Dockerfile` but optimized for basic use case
- Use default dependencies (no profile needed - simple-chat doesn't require cloud SDKs)
- Copy `install/default-config/` as `/app/config/` (same as tarball approach)
- Download and include `granite4:1b` model during build (using same logic as build-tarball.sh)
- Copy model to `/app/models/` directory
- Include entrypoint that uses the config directory
- Smaller image by excluding unused adapters/configs

### 2. Create Adapter Configuration Override

- **File**: `docker/config/adapters/passthrough-basic.yaml`
- Copy from `install/default-config/adapters/passthrough.yaml`
- Keep only `simple-chat` adapter enabled
- This file will be copied over the default config during Docker build to disable other adapters

### 3. Create Build and Publish Script

- **File**: `docker/publish-basic.sh`
- Build the basic Docker image with proper tagging
- Download granite4:1b model during build (using install/download_hf_gguf_model.py)
- Tag as `schmitech/orbit:basic` and `schmitech/orbit:latest` (or user preference)
- Push to Docker Hub
- Include error handling and authentication checks
- Support version tagging (e.g., `schmitech/orbit:basic-v1.0.0`)
- Follow similar structure to build-tarball.sh for consistency

### 4. Create Minimal Entrypoint Script

- **File**: `docker/docker-entrypoint-basic.sh`
- Simple entrypoint that ensures model exists and starts the server
- Uses `/app/config/config.yaml` (from default-config)
- Handles model verification

### 5. Create Quick Start Documentation

- **File**: `docker/README-BASIC.md`
- Quick start guide for pulling and running the basic image
- Instructions showing it's self-contained (no API keys needed)
- Example docker run commands
- Example API requests to test the simple-chat adapter
- Link from main README

### 6. Update Main README

- **File**: `docker/README.md`
- Add section about the basic image
- Link to quick start guide
- Include Docker Hub pull command

## Files to Create/Modify

### New Files:

1. `docker/Dockerfile.basic` - Optimized Dockerfile for basic image
2. `docker/config/adapters/passthrough-basic.yaml` - Only simple-chat enabled
3. `docker/publish-basic.sh` - Build and publish script
4. `docker/docker-entrypoint-basic.sh` - Entrypoint script
5. `docker/README-BASIC.md` - Quick start guide

### Modified Files:

1. `docker/README.md` - Add basic image section

## Key Configuration Details

### Adapters to Enable:

- `simple-chat` (from passthrough.yaml)
- Uses: llama_cpp (default inference provider)
- No additional dependencies beyond default profile
- Disable all other adapters by overriding passthrough.yaml

### Model Inclusion:

- Download `granite4:1b` model during Docker build
- Use `install/download_hf_gguf_model.py` script (same as tarball)
- Copy model to `/app/models/` in the image
- Model will be available immediately on container start

### Configuration Strategy:

- Copy `install/default-config/` to `/app/config/` (same as tarball)
- Override `adapters/passthrough.yaml` with minimal version containing only simple-chat
- Keep all other default-config files as-is
- No need for custom config.yaml - use default structure

### Dependencies:

- Use default profile (no --profile flag needed)
- Core dependencies only (llama-cpp-python for local inference)
- No cloud SDKs required

### Environment Variables:

- `ORBIT_DEFAULT_ADMIN_PASSWORD` (for admin access)
- No external API keys needed - fully self-contained with local model

## Publishing Workflow

1. Build image: `./docker/publish-basic.sh --build`

- Downloads granite4:1b GGUF model during build
- Creates optimized basic image with model included
- Uses default-config structure

2. Test locally: `docker run -p 3000:3000 schmitech/orbit:basic`

- No API keys needed - completely self-contained!
- Just pull and run
- Model is included in image

3. Publish: `./docker/publish-basic.sh --publish`
4. Tag version: `./docker/publish-basic.sh --publish --tag v1.0.0`

## Differences from Original Plan

- Uses `default-config` directly (like tarball) instead of creating minimal config files
- Only overrides `passthrough.yaml` to disable other adapters
- Includes granite4:1b model in image (like tarball includes it)
- No cloud profile needed (simple-chat uses local llama_cpp)
- Follows build-tarball.sh structure for consistency