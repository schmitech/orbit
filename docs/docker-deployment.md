# ORBIT - Docker Deployment

This repository contains Docker configuration files for running the ORBIT RAG (Retrieval-Augmented Generation) system with Ollama and MongoDB.

## System Components

- **ORBIT Server**: FastAPI application that handles retrieval and generation
- **Ollama**: Local inference server for running LLMs (must be running externally)
- **MongoDB**: Database for storing API keys and other metadata (must be running externally)

## Prerequisites

- Docker
- Docker Compose
- 8GB+ RAM
- GPU (optional but recommended for better performance)
- Ollama running externally
- MongoDB running externally

## Quick Start

### First-time Setup

1. Clone this repository
2. Make the initialization and setup scripts executable:
   ```bash
   chmod +x docker-init.sh docker-setup-db.sh
   ```
3. Create and configure your environment files:
   ```bash
   # Copy the example config and env files
   cp config.yaml.example config.yaml
   cp .env.example .env
   
   # Edit the files with your settings
   # config.yaml - Configure your server settings
   # .env - Add your API keys and credentials
   ```
4. Initialize the environment and build the image:
   ```bash
   ./docker-init.sh --build
   ```
5. Set up a sample database (choose either chroma or sqlite):
   ```bash
   ./docker-setup-db.sh chroma
   ```

### Regular Usage

- Start the containers (after stopping):
  ```bash
  ./docker-init.sh
  ```

- Stop the environment:
  ```bash
  docker compose down
  ```

### Making Changes

- After changing `config.yaml`:
  ```bash
  docker compose restart orbit-server
  ```

- After changing code or `requirements.txt`:
  ```bash
  ./docker-init.sh --build
  ```

- View logs:
  ```bash
  docker compose logs -f orbit-server
  ```

## Configuration Management

### Updating Configuration

There are several ways to update the configuration after deployment:

1. **Direct File Edit** (Recommended for most changes):
   - Edit `config.yaml` on your host machine
   - Restart the container:
     ```bash
     docker compose restart orbit-server
     ```

2. **Environment Variables**:
   - Create a `.env` file or set environment variables:
     ```bash
     ORBIT_CONFIG_GENERAL_PORT=4000
     ORBIT_CONFIG_LOGGING_LEVEL=DEBUG
     ```
   - Restart the container:
     ```bash
     docker compose restart orbit-server
     ```

3. **Docker Compose Override**:
   - Create `docker-compose.override.yml`:
     ```yaml
     services:
       orbit-server:
         environment:
           - ORBIT_CONFIG_GENERAL_PORT=4000
     ```
   - Restart the container:
     ```bash
     docker compose restart orbit-server
     ```

### When to Rebuild the Image

You need to rebuild the image (`docker compose up --build`) when:
- Making changes to the application code
- Updating `requirements.txt`
- Modifying the `Dockerfile`

You do NOT need to rebuild when:
- Updating `config.yaml` (mounted volume)
- Changing environment variables
- Modifying mounted volumes (chroma_db, sqlite_db, logs)

### Environment Variable Naming

Configuration overrides use this pattern:
- `ORBIT_CONFIG_` prefix
- Section name in uppercase
- Subsection name in uppercase
- All joined with underscores

Examples:
- `general.port` → `ORBIT_CONFIG_GENERAL_PORT`
- `logging.level` → `ORBIT_CONFIG_LOGGING_LEVEL`
- `embedding.provider` → `ORBIT_CONFIG_EMBEDDING_PROVIDER`

## Common Issues and Solutions

### Permission Issues

If you encounter permission errors like:
```
open /Users/username/.docker/buildx/current: permission denied
```

Fix it by running:
```bash
sudo chown -R $USER ~/.docker
```

### Container Build Process

The system requires the orbit-server container to be built. If you only see the image but no running container, run:
```bash
docker compose up --build
```

### Verifying Installation

Check if containers are running:
```bash
docker compose ps
```

You should see the orbit-server container in the running state.

## Configuration

The system is configured using the `config.yaml` file. The Docker setup provides a pre-configured `docker-config.yaml` that is copied to `config.yaml` during initialization if the file doesn't exist.

Environment variables can be set in the `.env` file:

```
MONGODB_USERNAME=admin
MONGODB_PASSWORD=password
OPENAI_API_KEY=your_key_here
...
```

## Components

### ORBIT Server

The ORBIT server is a FastAPI application that provides an API for:
- Querying the RAG system
- Managing API keys
- Managing collections

### External Services

The system expects the following services to be running externally:

#### Ollama
- Must be accessible at the host specified by `OLLAMA_HOST` (defaults to localhost)
- Required models:
  - gemma3:1b - Used for inference
  - nomic-embed-text - Used for embeddings

#### MongoDB
- Must be accessible at the host specified by `MONGODB_HOST` (defaults to localhost)
- Default credentials:
  - Username: admin
  - Password: password
- These can be changed in the `.env` file

## Usage

After setting up the sample database, you'll get API keys for accessing different collections. You can use these keys with the Python client as shown in the output of the setup script.

## Directory Structure

- `chroma_db`: Persistent storage for Chroma vector database
- `sqlite_db`: Persistent storage for SQLite database
- `logs`: Server log files

## Common Commands

- Start the system: `docker compose up -d`
- Stop the system: `docker compose down`
- View logs: `docker compose logs -f orbit-server`
- Restart server: `docker compose restart orbit-server`
- Shell into server: `docker exec -it orbit-server bash`

### Removing Images and Containers

To completely remove the system and start fresh:
```bash
# Stop and remove containers
docker compose down

# Remove the orbit-server image
docker rmi orbit-server:latest

# Remove all unused images (optional)
docker image prune -f

# Rebuild and start
docker compose up --build
```

## Troubleshooting

### Port Conflicts

If you have port conflicts, edit the `config.yaml` file to change the port or use environment variables to override it.

### Connection Issues

Make sure the configuration properly references your external Ollama and MongoDB services by their correct hostnames and ports.

### Build Issues

If you encounter build issues:
1. Check Docker logs: `docker compose logs`
2. Ensure all required files are present
3. Try rebuilding: `docker compose up --build --force-recreate`