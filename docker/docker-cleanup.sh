#!/bin/bash

echo "Stopping all running containers..."
docker stop $(docker ps -q)

echo "Removing all containers..."
docker rm $(docker ps -a -q)

echo "Removing all images..."
docker rmi -f $(docker images -q)

echo "Removing unused volumes..."
docker volume prune -f

echo "Removing unused networks..."
docker network prune -f

echo "Docker cleanup complete!" 

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

echo "\n==== Docker State After Cleanup ===="
echo "\nContainers:"
docker ps -a

echo "\nImages:"
docker images

echo "\nVolumes:"
docker volume ls

echo "\nNetworks:"
docker network ls 