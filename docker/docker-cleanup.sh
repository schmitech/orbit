#!/bin/bash

echo "=== Docker Cleanup Script ==="
echo "This script will perform a comprehensive Docker cleanup to fix storage corruption issues."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Warning: This script should be run with sudo for complete cleanup"
    echo "Some operations may fail without root privileges"
fi

echo "Stopping all running containers..."
docker stop $(docker ps -q) 2>/dev/null || true

echo "Removing all containers..."
docker rm $(docker ps -a -q) 2>/dev/null || true

echo "Removing all images..."
docker rmi -f $(docker images -q) 2>/dev/null || true

echo "Removing unused volumes..."
docker volume prune -f

echo "Removing unused networks..."
docker network prune -f

echo "Performing system prune (removes all unused data)..."
docker system prune -a -f --volumes

echo "Cleaning up Docker builder cache..."
docker builder prune -a -f

echo "Docker cleanup complete!" 

# Additional cleanup for overlay2 corruption issues
echo "Performing additional cleanup for overlay2 corruption..."

# Stop Docker daemon to ensure clean state
echo "Stopping Docker daemon..."
sudo systemctl stop docker 2>/dev/null || true

# Clean up potential corrupted overlay2 directories
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
echo "Docker root directory: $DOCKER_ROOT"

if [ -d "$DOCKER_ROOT/overlay2" ]; then
    echo "Cleaning up overlay2 directory..."
    # Remove corrupted symlinks and empty directories
    find "$DOCKER_ROOT/overlay2" -type l -exec test ! -e {} \; -delete 2>/dev/null || true
    find "$DOCKER_ROOT/overlay2" -type d -empty -delete 2>/dev/null || true
fi

# Restart Docker daemon
echo "Starting Docker daemon..."
sudo systemctl start docker 2>/dev/null || true

# Wait for Docker to be ready
echo "Waiting for Docker to be ready..."
sleep 5

echo "Checking for open Docker-related ports (3000, 5432, 6379, 8000, 8080, 9000)..."
PORTS=(3000 5432 6379 8000 8080 9000)
ANY_OPEN=false
for PORT in "${PORTS[@]}"; do
    if lsof -i :$PORT &>/dev/null; then
        echo "Port $PORT is still in use!"
        ANY_OPEN=true
    fi
done
if [ "$ANY_OPEN" = false ]; then
    echo "All checked ports are free. Cleanup successful!"
else
    echo "Some ports are still in use. Please investigate running processes."
fi 

echo -e "\n==== Docker State After Cleanup ===="
echo -e "\nContainers:"
docker ps -a

echo -e "\nImages:"
docker images

echo -e "\nVolumes:"
docker volume ls

echo -e "\nNetworks:"
docker network ls

echo -e "\nDocker system info:"
docker system df

echo -e "\n=== Cleanup Complete ==="
echo "If you still experience issues, consider:"
echo "1. Restarting the Docker daemon: sudo systemctl restart docker"
echo "2. Checking Docker logs: sudo journalctl -u docker"
echo "3. As a last resort, completely removing Docker data: sudo rm -rf /var/lib/docker" 