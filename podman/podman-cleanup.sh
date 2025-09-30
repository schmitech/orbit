#!/bin/bash

echo "=== Podman Cleanup Script ==="
echo "This script performs a thorough Podman cleanup to recover disk space or fix stale state."

if ! command -v podman >/dev/null 2>&1; then
    echo "Podman is not installed. Aborting."
    exit 1
fi

echo "Stopping all running containers..."
podman stop $(podman ps -q) 2>/dev/null || true

echo "Removing all containers..."
podman rm $(podman ps -a -q) 2>/dev/null || true

echo "Removing all images..."
podman rmi -f $(podman images -q) 2>/dev/null || true

echo "Removing unused volumes..."
podman volume prune -f

echo "Removing unused networks..."
podman network prune -f

echo "Pruning system data..."
podman system prune -a -f --volumes

echo "Pruning build cache..."
podman builder prune -a -f

if command -v podman-machine >/dev/null 2>&1; then
    echo "Checking Podman machine state..."
    RUNNING_MACHINE=$(podman machine list --format '{{.Name}} {{.Running}}' | awk '$2 == "true" {print $1}')
    if [ -n "$RUNNING_MACHINE" ]; then
        echo "Stopping Podman machine $RUNNING_MACHINE..."
        podman machine stop "$RUNNING_MACHINE"
    fi
    echo "You can reclaim additional disk space with: podman machine prune"
fi

GRAPH_ROOT=$(podman info --format '{{.Store.GraphRoot}}' 2>/dev/null)
if [ -n "$GRAPH_ROOT" ] && [ -d "$GRAPH_ROOT" ]; then
    echo "Podman storage directory: $GRAPH_ROOT"
fi

PORTS=(3000 5432 6379 8000 8080 9000)
ANY_OPEN=false
for PORT in "${PORTS[@]}"; do
    if lsof -i :$PORT &>/dev/null; then
        echo "Port $PORT is still in use."
        ANY_OPEN=true
    fi
done
if [ "$ANY_OPEN" = false ]; then
    echo "All monitored ports are free."
fi

echo -e "\n==== Podman State After Cleanup ===="

echo -e "\nContainers:"; podman ps -a

echo -e "\nImages:"; podman images

echo -e "\nVolumes:"; podman volume ls

echo -e "\nNetworks:"; podman network ls

echo -e "\nDisk usage:"; podman system df

echo -e "\n=== Cleanup Complete ==="
echo "If issues persist consider:"
echo "1. podman system reset"
echo "2. Inspecting podman logs (journalctl --user -u podman)"
echo "3. For Podman machine users: podman machine prune"
