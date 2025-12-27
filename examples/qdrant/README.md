# Docker Installation Guide for Amazon Linux

This guide covers the complete process of installing and configuring Docker on Amazon Linux.

## Prerequisites

- Amazon Linux system with sudo access
- Internet connectivity for package downloads

## Step 1: Update System Packages

First, update your system to ensure all packages are current:

```bash
sudo yum update -y
```

This command will:
- Update all installed packages to their latest versions
- Install any security patches
- Use the `-y` flag to automatically confirm updates

## Step 2: Install Docker

Install Docker using the yum package manager:

```bash
sudo yum install -y docker
```

This will install:
- Docker Engine (version 25.0.8)
- containerd (container runtime)
- runc (low-level container runtime)
- container-selinux (security policies)
- Required networking tools (iptables, etc.)

## Step 3: Start and Enable Docker Service

Start the Docker service and enable it to start automatically on boot:

```bash
# Start Docker service
sudo systemctl start docker

# Enable Docker to start on boot
sudo systemctl enable docker
```

## Step 4: Configure User Permissions

Add your user to the docker group to run Docker commands without sudo:

```bash
sudo usermod -a -G docker ec2-user
```

**Important**: You need to log out and log back in (or start a new shell session) for the group membership changes to take effect.

## Step 5: Verify Installation

Check that Docker is installed and running correctly:

```bash
# Check Docker version
sudo docker --version

# Check Docker service status
sudo systemctl status docker
```

Expected output:
- Docker version: `Docker version 25.0.8, build 0bab007`
- Service status: `active (running)`

## Step 6: Test Docker (After Re-login)

After logging back in, test Docker without sudo:

```bash
# Check version without sudo
docker --version

# Run a test container
docker run hello-world
```

## Installation Summary

✅ **Completed Tasks:**
- System packages updated
- Docker 25.0.8 installed with all dependencies
- Docker service started and enabled for auto-start
- User added to docker group for sudo-free access
- Installation verified and confirmed working

## Next Steps

Docker is now ready for use! You can:
- Pull images from Docker Hub: `docker pull <image-name>`
- Run containers: `docker run <image-name>`
- Build custom images: `docker build -t <tag> .`
- Manage containers: `docker ps`, `docker stop`, `docker rm`

## Troubleshooting

If you encounter permission issues:
1. Ensure you've logged out and back in after adding user to docker group
2. Verify group membership: `groups $USER`
3. Check if Docker service is running: `sudo systemctl status docker`

For more information, visit the [official Docker documentation](https://docs.docker.com/).

---

# Installing Qdrant Vector Database with Docker

This section covers installing and running Qdrant vector database using Docker.

## Prerequisites

- Docker installed and running (see above steps)
- Port 6333 available for Qdrant API
- Port 6334 available for Qdrant gRPC (optional)

## Step 1: Pull Qdrant Docker Image

Pull the official Qdrant image from Docker Hub:

```bash
sudo docker pull qdrant/qdrant
```

This will download the latest Qdrant image with all dependencies.

## Step 2: Create Storage Directory

Create a local directory for persistent data storage:

```bash
mkdir -p qdrant
```

This directory will be mounted to the container to persist your vector data.

## Step 3: Run Qdrant Container

Start the Qdrant container with proper configuration:

```bash
sudo docker run -p 6333:6333 \
    -v $(pwd)/qdrant:/qdrant/storage \
    qdrant/qdrant
```

This command:
- Maps port 6333 (REST API) from container to host
- Mounts local `qdrant/` directory to container's `/qdrant/storage`
- Runs the container in foreground (use `-d` flag for background)

## Step 4: Verify Qdrant Installation

Check that Qdrant is running correctly:

```bash
# Check running containers
sudo docker ps

# Test Qdrant API
curl http://localhost:6333/
```

Expected output:
```json
{"title":"qdrant - vector search engine","version":"1.14.1","commit":"530430fac2a3ca872504f276d2c91a5c91f43fa0"}
```

## Qdrant Service Details

✅ **Installation Results:**
- **Version**: Qdrant 1.14.1
- **REST API**: `http://localhost:6333/`
- **Web Dashboard**: `http://localhost:6333/dashboard`
- **gRPC API**: `localhost:6334` (if needed)
- **Data Storage**: Persistent in `~/qdrant/` directory
- **Features**: 
  - Distributed mode disabled (single node)
  - Telemetry reporting enabled
  - TLS disabled for REST API
  - Inference service not configured

## Qdrant Startup Output

When successfully started, you'll see:
```
           _                 _    
  __ _  __| |_ __ __ _ _ __ | |_  
 / _` |/ _` | '__/ _` | '_ \| __| 
| (_| | (_| | | | (_| | | | | |_  
 \__, |\__,_|_|  \__,_|_| |_|\__| 
    |_|                           

Version: 1.14.1, build: 530430fa
Access web UI at http://localhost:6333/dashboard
```

## Container Management

Useful commands for managing your Qdrant container:

```bash
# Run in background (detached mode)
sudo docker run -d -p 6333:6333 \
    -v $(pwd)/qdrant:/qdrant/storage \
    --name qdrant \
    qdrant/qdrant

# Stop container
sudo docker stop qdrant

# Start existing container
sudo docker start qdrant

# View logs
sudo docker logs qdrant

# Remove container
sudo docker rm qdrant
```

## Next Steps with Qdrant

Your Qdrant vector database is ready for use! You can now:

- **Create Collections**: Store and organize your vectors
- **Insert Vectors**: Add embeddings with metadata
- **Search Vectors**: Perform similarity searches
- **Use APIs**: REST API or gRPC for integration
- **Access Web UI**: Browse and manage data via dashboard

### Common API Operations

```bash
# Create a collection
curl -X PUT http://localhost:6333/collections/my_collection \
    -H "Content-Type: application/json" \
    -d '{"vectors": {"size": 384, "distance": "Cosine"}}'

# Insert a vector
curl -X PUT http://localhost:6333/collections/my_collection/points \
    -H "Content-Type: application/json" \
    -d '{"points": [{"id": 1, "vector": [0.1, 0.2, 0.3], "payload": {"text": "example"}}]}'
```

For more information, visit the [official Qdrant documentation](https://qdrant.tech/documentation/).

---

# Automating Qdrant Startup with a Shell Script

To simplify starting Qdrant in the background, you can use a shell script. This script ensures the storage directory exists and runs Qdrant as a named, detached Docker container.

## Step 1: Create the Script

Create a file named `start_qdrant.sh` with the following content:

```bash
#!/bin/bash
# Script to start Qdrant vector database in the background using Docker

# Ensure storage directory exists
mkdir -p "$(pwd)/qdrant"

# Run Qdrant in detached mode with a fixed container name
sudo docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v "$(pwd)/qdrant:/qdrant/storage" \
  qdrant/qdrant
```

Make the script executable:

```bash
chmod +x start_qdrant.sh
```

## Step 2: Start Qdrant in the Background

Run the script to start Qdrant as a background service:

```bash
./start_qdrant.sh
```

This will:
- Ensure the `qdrant/` storage directory exists
- Start Qdrant in detached mode (`-d`)
- Name the container `qdrant` for easy management

## Step 3: View Qdrant Logs

To view the logs for the running Qdrant container, use:

```bash
sudo docker logs -f qdrant
```

The `-f` flag will stream the logs live (similar to `tail -f`).

## Step 4: Stop the Qdrant Container

To stop the running Qdrant container, use:

```bash
sudo docker stop qdrant
```

This will gracefully stop the Qdrant service running in the background.

---

# Qdrant Utility Scripts

This directory contains Python utility scripts for managing Qdrant collections. All scripts support both **self-hosted Qdrant** and **Qdrant Cloud**.

## Available Scripts

| Script | Description |
|--------|-------------|
| `create_qdrant_collection.py` | Creates, populates, or updates collections from Q&A JSON files |
| `query_qdrant_collection.py` | Queries collections with semantic search |
| `list_qdrant_collections.py` | Lists all available collections |
| `delete_qdrant_collection.py` | Deletes a specified collection |

## Connection Modes

### Self-Hosted Qdrant (Default)

Uses `DATASOURCE_QDRANT_HOST` and `DATASOURCE_QDRANT_PORT` from your `.env` file.

```bash
# List collections from self-hosted Qdrant
python list_qdrant_collections.py

# Create a collection
python create_qdrant_collection.py city_faq data/city_faq.json

# Query a collection
python query_qdrant_collection.py city_faq "What are the parking rules?"

# Delete a collection
python delete_qdrant_collection.py city_faq
```

### Qdrant Cloud

Use the `--cloud` flag to connect to Qdrant Cloud. Requires `DATASOURCE_QDRANT_URL` and `DATASOURCE_QDRANT_API_KEY` in your `.env` file.

```bash
# List collections from Qdrant Cloud
python list_qdrant_collections.py --cloud

# Create a collection on Qdrant Cloud
python create_qdrant_collection.py city_faq data/city_faq.json --cloud

# Query a collection on Qdrant Cloud
python query_qdrant_collection.py city_faq "What are the parking rules?" --cloud

# Delete a collection from Qdrant Cloud
python delete_qdrant_collection.py city_faq --cloud
```

### Update Mode (Cost-Saving)

Use the `--update` flag to add new records to an existing collection without deleting and re-creating it. This saves embedding costs when using paid services like OpenAI.

```bash
# Add more records to an existing collection (self-hosted)
python create_qdrant_collection.py city_faq data/new_qa_pairs.json --update

# Add more records to a Qdrant Cloud collection
python create_qdrant_collection.py city_faq data/new_qa_pairs.json --cloud --update
```

**How it works:**
- Finds the highest existing ID in the collection
- Assigns new IDs starting from max_id + 1
- Only embeds and uploads the new records
- Preserves all existing data in the collection

## Environment Variables

Add these to your `.env` file based on your connection mode:

```bash
# For self-hosted Qdrant (default)
DATASOURCE_QDRANT_HOST=localhost
DATASOURCE_QDRANT_PORT=6333

# For Qdrant Cloud (--cloud flag)
DATASOURCE_QDRANT_URL=https://your-cluster-id.region.cloud.qdrant.io:6333
DATASOURCE_QDRANT_API_KEY=your-qdrant-api-key
```

For more information, visit the [official Qdrant documentation](https://qdrant.tech/documentation/).
