#!/bin/bash

echo "Setting up Docker storage and permissions..."

# Stop Docker service
sudo systemctl stop docker

# Create Docker directory structure
sudo mkdir -p /opt/dlami/nvme/docker/tmp
sudo mkdir -p /opt/dlami/nvme/docker/overlay2
sudo mkdir -p /opt/dlami/nvme/docker/containers

# Set proper permissions
sudo chown -R root:root /opt/dlami/nvme/docker
sudo chmod -R 711 /opt/dlami/nvme/docker

# Ensure Docker daemon configuration exists
if [ ! -f /etc/docker/daemon.json ]; then
    sudo mkdir -p /etc/docker
    echo '{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    },
    "data-root": "/opt/dlami/nvme/docker"
}' | sudo tee /etc/docker/daemon.json
fi

# Start Docker service
sudo systemctl start docker

# Wait for Docker to be ready
echo "Waiting for Docker service to be ready..."
sleep 5

# Verify Docker is running and using correct directory
echo "Verifying Docker configuration..."
docker info | grep "Docker Root Dir"

# Clean up any stale Docker resources
echo "Cleaning up Docker resources..."
docker system prune -f

# Pull the vLLM image in advance
echo "Pulling vLLM Docker image..."
docker pull vllm/vllm-openai:latest

echo "Setup complete! You can now run ./run_vllm.sh" 