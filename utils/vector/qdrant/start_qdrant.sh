#!/bin/bash
# Script to start Qdrant vector database in the background using Docker

CONTAINER_NAME="qdrant"

# Stop and remove the container if it already exists
if [ "$(sudo docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Stopping and removing existing container: ${CONTAINER_NAME}"
    sudo docker stop ${CONTAINER_NAME}
    sudo docker rm ${CONTAINER_NAME}
fi

echo "Starting a new ${CONTAINER_NAME} container..."

# Ensure storage directory exists
mkdir -p "$(pwd)/qdrant"

# Run Qdrant in detached mode with a fixed container name
sudo docker run -d \
  --name ${CONTAINER_NAME} \
  -p 6333:6333 \
  -v "$(pwd)/qdrant:/qdrant/storage" \
  qdrant/qdrant

echo "Qdrant container started successfully." 