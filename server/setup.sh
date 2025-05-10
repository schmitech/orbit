#!/bin/bash

# =============================================================================
# Orbit Server Setup Script
# =============================================================================
#
# This script sets up the development environment for the Orbit server.
#
# Requirements:
#   - Python 3.12
#   - Bash shell
#   - Internet connection (for downloading dependencies and models)
#
# Features:
#   - Creates a Python virtual environment
#   - Installs required Python packages from requirements.txt
#   - Optional: Installs llama-cpp-python and downloads Gemma 3 1B GGUF model
#   - Sets up .env file from template if it doesn't exist
#
# Usage:
#   Basic setup (without llama-cpp):
#     ./setup.sh
#
#   Full setup (with llama-cpp and GGUF model):
#     ./setup.sh --install-llama-cpp
#
# After running:
#   - Activate the virtual environment: source venv/bin/activate
#   - The server will be ready to run with all dependencies installed
#
# =============================================================================

# Exit on error
set -e

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    case $color in
        "red") echo -e "\033[0;31m$message\033[0m" ;;
        "green") echo -e "\033[0;32m$message\033[0m" ;;
        "yellow") echo -e "\033[0;33m$message\033[0m" ;;
        *) echo "$message" ;;
    esac
}

# Function to download GGUF model
download_gguf_model() {
    print_message "yellow" "Downloading Gemma 3 1B GGUF model..."
    
    # Create gguf directory if it doesn't exist
    mkdir -p gguf
    
    # Download the model
    if ! curl -L "https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_0.gguf" -o "gguf/gemma-3-1b-it-Q4_0.gguf"; then
        print_message "red" "Error: Failed to download GGUF model."
        exit 1
    fi
    
    print_message "green" "GGUF model downloaded successfully."
}

# Default value for INSTALL_LLAMA_CPP
INSTALL_LLAMA_CPP=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --install-llama-cpp)
            INSTALL_LLAMA_CPP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Print initial status about llama-cpp
if [ "$INSTALL_LLAMA_CPP" = false ]; then
    print_message "yellow" "Note: llama-cpp-python will be skipped during installation. Use --install-llama-cpp to include it."
fi

# Check if Python 3.12 is installed
if ! command -v python3 &> /dev/null; then
    print_message "red" "Error: Python 3.12 is not installed. Please install Python 3.12 first."
    exit 1
fi

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    print_message "red" "Error: requirements.txt not found in the current directory."
    exit 1
fi

print_message "yellow" "Setting up Python virtual environment..."

# Create virtual environment
if ! python3 -m venv venv; then
    print_message "red" "Error: Failed to create virtual environment."
    exit 1
fi

print_message "green" "Virtual environment created successfully."

# Activate virtual environment
print_message "yellow" "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_message "yellow" "Upgrading pip..."
if ! pip install --upgrade pip; then
    print_message "red" "Error: Failed to upgrade pip."
    exit 1
fi

# Create temporary requirements file without llama-cpp-python if not installing it
if [ "$INSTALL_LLAMA_CPP" = false ]; then
    print_message "yellow" "Skipping llama-cpp-python installation..."
    grep -v "llama-cpp-python" requirements.txt > requirements_temp.txt
    mv requirements_temp.txt requirements_temp.txt
else
    print_message "yellow" "Including llama-cpp-python in installation..."
    cp requirements.txt requirements_temp.txt
fi

# Install requirements
print_message "yellow" "Installing requirements..."
if ! pip install -r requirements_temp.txt; then
    print_message "red" "Error: Failed to install requirements."
    rm -f requirements_temp.txt
    exit 1
fi

# Clean up temporary file
rm -f requirements_temp.txt

# Download GGUF model if llama-cpp is enabled
if [ "$INSTALL_LLAMA_CPP" = true ]; then
    download_gguf_model
fi

if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    cp .env.example .env
    print_message "green" "Created .env from template."
else
    if [ ! -f ".env.example" ]; then
        print_message "red" "Warning: .env.example not found."
    elif [ -f ".env" ]; then
        print_message "yellow" ".env already exists, skipping."
    fi
fi

print_message "green" "Setup completed successfully!"
print_message "yellow" "To activate the virtual environment, run: source venv/bin/activate"
