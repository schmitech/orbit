#!/bin/bash

set -e

# Parse command line arguments
BUILD=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --build) BUILD=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "🚀 Initializing Orbit Docker environment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check for required files
if [ ! -f "config.yaml" ]; then
    echo "❌ config.yaml not found. Please create a config.yaml file first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "❌ .env file not found. Please create a .env file with your credentials."
    exit 1
fi

# Create necessary directories
echo "📁 Creating required directories..."
mkdir -p logs

# Build or start Docker containers
if [ "$BUILD" = true ]; then
    echo "🔨 Building and starting Docker containers..."
    docker compose up -d --build
else
    echo "🐳 Starting Docker containers..."
    docker compose up -d
fi

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 5

# Display status information
echo "📊 Service status:"
docker compose ps

echo "
🎉 Orbit Docker environment initialized successfully!

To interact with your Orbit system:

1. Server is accessible at: http://localhost:3000

For logs, check the 'logs' directory or run:
docker compose logs -f orbit-server

To shut down the environment:
docker compose down

To rebuild the image:
./docker-init.sh --build

Happy orbiting! 🚀
"