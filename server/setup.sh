#!/bin/bash

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

# Check if Python 3.13 is installed
if ! command -v python3.13 &> /dev/null; then
    print_message "red" "Error: Python 3.13 is not installed. Please install Python 3.13 first."
    exit 1
fi

# Check if requirements.txt exists
if [ ! -f "requirements.txt" ]; then
    print_message "red" "Error: requirements.txt not found in the current directory."
    exit 1
fi

print_message "yellow" "Setting up Python virtual environment..."

# Create virtual environment
if ! python3.13 -m venv venv; then
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

# Install requirements
print_message "yellow" "Installing requirements..."
if ! pip install -r requirements.txt; then
    print_message "red" "Error: Failed to install requirements."
    exit 1
fi

# Copy configuration files
print_message "yellow" "Copying configuration files..."
if [ -f "config.yaml.example" ] && [ ! -f "config.yaml" ]; then
    cp config.yaml.example config.yaml
    print_message "green" "Created config.yaml from template."
else
    if [ ! -f "config.yaml.example" ]; then
        print_message "red" "Warning: config.yaml.example not found."
    elif [ -f "config.yaml" ]; then
        print_message "yellow" "config.yaml already exists, skipping."
    fi
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
